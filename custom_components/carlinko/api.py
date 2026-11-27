"""CarLinko client facade: orchestrates the cloud and BLE transports for one account/vehicle.

The heavy lifting lives in the layers this ties together:

- :mod:`.cloud` — request signing, login and signed GET/POST (the cloud pipe).
- :mod:`.ble` — the BLE pipe (55AA framing, CRC, control/enrol/status exchanges).
- :mod:`.blob` — decoding the status blob (identical from either pipe).
- :mod:`.capabilities` — per-model metadata and capability flags from `/user/vehicle`.

This module only decides *which pipe* carries a command or telemetry read and merges the results.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import aiohttp

from .ble import CarLinkoBleError, CarLinkoBleUnavailable, is_status_body
from .blob import decode_blob, decode_control_config, is_plausible, parse_fw_version
from .capabilities import (
    VehicleControlConfig,
    VehicleInfo,
    parse_vehicle_control_config,
)
from .cloud import CarLinkoConnectionError, CarLinkoDeviceOfflineError, CloudTransport
from .const import (
    CMD_AC_SET_TEMPERATURE_PREFIX,
    DEFAULT_TRANSPORT_MODE,
    TRANSPORT_BLE,
    TRANSPORT_BLE_CLOUD,
    TRANSPORT_CLOUD,
)

_LOGGER = logging.getLogger(__name__)

# How long a status blob read back right after a control stays usable for the follow-up poll.
_FRESH_BLOB_TTL = 20.0

# Wait after a cloud control before reading state back: the POST returns on delivery, not actuation.
_POST_CONTROL_DELAY = 2.0

# Authorization sentinel used for enrol when the account has no expiry window (owner accounts).
BLE_AUTH_OWNER = 0xFFFFFFFF


class CarLinkoClient:
    """Talks to a single CarLinko account over the cloud and (optionally) BLE transports."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        region: str,
        time_zone: str,
        transport_mode: str = DEFAULT_TRANSPORT_MODE,
        device_sn: str | None = None,
        ble_send: Callable[[str], Awaitable[str | None]] | None = None,
        ble_read: Callable[[], Awaitable[tuple[str, str, str] | None]] | None = None,
    ) -> None:
        self._cloud = CloudTransport(session, email, password, region, time_zone)
        self._transport_mode = transport_mode
        self._device_sn = device_sn
        # BLE transport callables, injected by __init__.py (keep this client HA/bleak-free).
        self._ble_send = ble_send
        self._ble_read = ble_read
        # Status blob a control read back right after acting (with its source + monotonic timestamp):
        # the next telemetry poll uses it instead of opening a fresh read.
        self._fresh_blob: tuple[float, str, str] | None = None
        # Last decoded firmware version, reused when a poll can't re-read it (e.g. the post-control blob).
        self._last_fw: str | None = None
        self._control_config: VehicleControlConfig | None = None

    def set_ble_transport(
        self,
        ble_send: Callable[[str], Awaitable[str | None]] | None,
        ble_read: Callable[[], Awaitable[tuple[str, str, str] | None]] | None,
    ) -> None:
        """Wire the BLE transport callables (built in __init__.py, which has the hass/bleak context)."""
        self._ble_send = ble_send
        self._ble_read = ble_read

    async def login(self) -> str:
        """Log in with the stored account, return + cache the new session token."""
        return await self._cloud.login()

    async def get_user_id(self) -> str:
        """Fetch the account's userId (`/user/info` -> data.id), needed for BLE control."""
        data = await self._cloud.signed_get("/user/info")
        info = data.get("data") or {}
        user_id = info.get("id") if isinstance(info, dict) else None
        if user_id is None:
            raise CarLinkoConnectionError(f"/user/info has no id: {data}")
        return str(user_id)

    # ---- /user/vehicle/remoteControl — actuation commands ----

    def _stash_fresh_blob(self, blob: str | None, source: str) -> None:
        """Remember the status a control read back, so the next poll reflects it without re-reading."""
        if blob:
            self._fresh_blob = (time.monotonic(), blob, source)

    def _take_fresh_blob(self) -> tuple[str, str] | None:
        """Pop the post-control (blob, source) if it is still recent; it is consumed either way."""
        if self._fresh_blob is None:
            return None
        timestamp, blob, source = self._fresh_blob
        self._fresh_blob = None
        if time.monotonic() - timestamp <= _FRESH_BLOB_TTL:
            return blob, source
        return None

    async def _cloud_control(self, vehicle_id: str, device_sn: str, opcode: str, timeout: int) -> None:
        """Post a control over the cloud, then read state back so the next poll reflects the action.

        Unlike BLE (where the car pushes a status update on its own), the cloud returns on delivery
        and sends nothing further, so we wait for the car to actuate and read the status explicitly.
        """
        await self._cloud.post_remote_control(vehicle_id, device_sn, opcode, timeout)
        await asyncio.sleep(_POST_CONTROL_DELAY)
        try:
            self._stash_fresh_blob(await self._cloud.query(vehicle_id, device_sn, "77"), "cloud")
        except CarLinkoConnectionError:
            _LOGGER.debug("cloud control %s: follow-up status not captured; next poll will refresh", opcode)

    async def _send_remote_command(self, vehicle_id: str, device_sn: str, opcode: str, timeout: int = 20) -> None:
        """Send a remote-control opcode over the configured transport.

        - ``cloud``: cloud only.
        - ``ble_cloud``: BLE when the car is in range, cloud when it is out of range.
        - ``ble``: BLE only (no cloud fallback — for when the cloud account is not enabled).
        """
        mode = self._transport_mode
        _LOGGER.debug("remote command %s via transport %s", opcode, mode)

        if mode in (TRANSPORT_BLE, TRANSPORT_BLE_CLOUD) and self._ble_send is not None:
            try:
                self._stash_fresh_blob(await self._ble_send(opcode), "ble")
                _LOGGER.debug("remote command %s sent over BLE", opcode)
                return
            except CarLinkoBleUnavailable as err:
                if mode == TRANSPORT_BLE:
                    _LOGGER.debug("remote command %s: BLE unavailable (%s); BLE-only, no fallback", opcode, err)
                    raise
                _LOGGER.debug("remote command %s: BLE unavailable (%s); falling back to cloud", opcode, err)
                await self._cloud_control(vehicle_id, device_sn, opcode, timeout)
                return

        if mode == TRANSPORT_BLE:
            raise CarLinkoBleUnavailable("BLE-only mode but the BLE transport is not configured")

        # Cloud only.
        await self._cloud_control(vehicle_id, device_sn, opcode, timeout)

    async def send_control(self, vehicle_id: str, device_sn: str, opcode: str) -> None:
        """Send a remote-control opcode (the actuation entry point for every platform entity)."""
        await self._send_remote_command(vehicle_id, device_sn, opcode)

    async def set_ac_temperature(self, vehicle_id: str, device_sn: str, target_temp_c: float) -> None:
        """Send an A/C target temperature: raw °C, or (°C × 2) | 0x80 on half-degree-step cars."""
        step = self._control_config.ac_temp_step if self._control_config else None
        raw = int(round(target_temp_c * 2)) | 0x80 if step == 0.5 else int(round(target_temp_c))
        opcode = f"{CMD_AC_SET_TEMPERATURE_PREFIX}{raw & 0xFF:02x}"
        await self._send_remote_command(vehicle_id, device_sn, opcode)

    # ---- /user/vehicle — vehicle list + per-model vehicleControlConfig ----

    async def get_vehicles(self) -> list[VehicleInfo]:
        """List vehicles on this account."""
        data = await self._cloud.signed_get("/user/vehicle")
        raw = data.get("data")
        items = raw if isinstance(raw, list) else ([raw] if raw else [])
        vehicles = []
        for v in items:
            if not v.get("vehicleId"):
                continue
            img_cfg = json.loads(v["vehicleImgConfig"])
            vehicles.append(
                VehicleInfo(
                    vehicle_id=str(v.get("vehicleId")),
                    device_sn=v.get("deviceId"),
                    model=v.get("model"),
                    brand=v.get("brand"),
                    plate=v.get("licenseNumber"),
                    img_front=img_cfg["Front"],
                    img_side=img_cfg["Side"],
                    img_top=img_cfg["Top"],
                    vin=v.get("vin") or "",
                )
            )
        return vehicles

    async def get_vehicle_control_config(self, vehicle_id: str) -> VehicleControlConfig:
        """Fetch vehicleControlConfig once; it's per-model and doesn't change."""
        if self._control_config is not None:
            return self._control_config
        data = await self._cloud.signed_get("/user/vehicle")
        raw = data.get("data")
        items = raw if isinstance(raw, list) else ([raw] if raw else [])
        vehicle = next((v for v in items if str(v.get("vehicleId")) == str(vehicle_id)), None)
        self._control_config = parse_vehicle_control_config((vehicle or {}).get("vehicleControlConfig"))
        return self._control_config

    async def ble_auth_remaining(self, vehicle_id: str) -> int | None:
        """Authorization seconds for the user-enroll command, from ``/user/vehicle``.

        An owner account has no expiry window and uses the infinite sentinel; a shared account uses the
        seconds its master granted (``endTime - now``, UTC). Returns None if it can't be fetched or
        parsed; an already-enrolled userId still controls fine, since enrolment persists in the car.
        """
        try:
            data = await self._cloud.signed_get("/user/vehicle")
        except CarLinkoConnectionError:
            return None
        raw = data.get("data")
        items = raw if isinstance(raw, list) else ([raw] if raw else [])
        vehicle = next((v for v in items if str(v.get("vehicleId")) == str(vehicle_id)), None)
        if vehicle is None:
            return None
        if vehicle.get("owner"):
            return BLE_AUTH_OWNER
        end_time = vehicle.get("endTime")
        if not end_time:
            return None
        try:
            end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return None
        seconds = int((end - datetime.now(UTC)).total_seconds())
        return min(BLE_AUTH_OWNER, max(0, seconds))

    # ---- telemetry read: 23 (fw location / app mode) -> 24 (fw version) -> 77 (status) ----

    def _decode_candidate(
        self, r23: str | None, r24: str | None, r77: str | None, source: str
    ) -> dict[str, Any] | None:
        """Decode one unified read into a tagged state, or None if it shouldn't be trusted.

        The ``0x23`` reply gates on app mode (``230002``); any other value means the car isn't
        serving normal telemetry, so the read is dropped. ``0x24`` carries the firmware version
        (cached), and ``0x77`` is the status blob, validated before decoding (same body as the BLE
        path, no 55AA/CRC wrapper on the cloud side).
        """
        if r23 != "230002":
            return None
        if not r77:
            return None
        try:
            raw = bytes.fromhex(r77)
        except ValueError:
            return None
        if not is_status_body(raw):
            return None
        data = decode_blob(r77, self._control_config)
        if not data or not is_plausible(data):
            # A corrupt / misaligned frame: drop it so it never reaches the sensors or poisons the
            # odometer freshness gate.
            return None
        fw = parse_fw_version(bytes.fromhex(r24)) if r24 else None
        if fw:
            self._last_fw = fw
        data.update(decode_control_config(self._control_config))
        data["fw_version"] = fw or self._last_fw
        data["source"] = source
        return data

    async def _cloud_state_candidate(self, vehicle_id: str) -> dict[str, Any] | None:
        """Decoded cloud telemetry for this cycle, tagged source='cloud'. None if unreachable/offline.

        Runs the same 23 -> 24 -> 77 sequence as BLE over ``/remoteControl`` (the cloud echoes each
        reply in ``data`` as ``deviceSn__<hex>``). Network/offline errors are swallowed only when BLE
        can still contribute; with no BLE source they propagate so the coordinator surfaces
        UpdateFailed. Auth errors always propagate.
        """
        if not self._device_sn:
            return None
        try:
            r23 = await self._cloud.query(vehicle_id, self._device_sn, "23")
            r24 = await self._cloud.query(vehicle_id, self._device_sn, "24")
            r77 = await self._cloud.query(vehicle_id, self._device_sn, "77")
        except CarLinkoDeviceOfflineError:
            # The T-box has no cellular link: no candidate, but not a failure — the coordinator keeps
            # the last-known values and flags the car offline (same as the old isOnline=False path).
            return None
        except CarLinkoConnectionError:
            if self._ble_read is not None:
                return None
            raise
        return self._decode_candidate(r23, r24, r77, "cloud")

    def _decode_fresh_blob(self, blob: str, source: str) -> dict[str, Any] | None:
        """Decode a status blob a just-completed control read back (last-known firmware, no app gate)."""
        try:
            raw = bytes.fromhex(blob)
        except ValueError:
            return None
        if not is_status_body(raw):
            return None
        data = decode_blob(blob, self._control_config)
        if not data or not is_plausible(data):
            return None
        data.update(decode_control_config(self._control_config))
        data["fw_version"] = self._last_fw
        data["source"] = source
        return data

    async def _ble_state_candidate(self, vehicle_id: str) -> dict[str, Any] | None:
        """Decoded BLE telemetry for this cycle, tagged source='ble'. None if out of range.

        Runs the full 23 -> 24 -> 77 read over a short-lived connection.
        """
        if self._ble_read is None:
            return None
        try:
            replies = await self._ble_read()
        except CarLinkoBleError:
            return None
        except Exception:  # BLE is a best-effort secondary source; never fail the update over it
            # Never let a BLE transport anomaly (a stray bleak/proxy error) escape and fail the whole
            # update: the cloud candidate and the last-known values must survive it.
            _LOGGER.warning("CarLinko BLE telemetry read failed; skipping BLE this cycle", exc_info=True)
            return None
        if not replies:
            return None
        r23, r24, r77 = replies
        return self._decode_candidate(r23, r24, r77, "ble")

    # ---- combined poll, one update cycle ----

    async def poll_telemetry(self, vehicle_id: str) -> list[dict[str, Any]]:
        """Poll one cycle; return a decoded state per reachable source (empty if none reached).

        The per-model control config lives on `/user/vehicle`, which answers even while the car
        has no signal, so fetch (and cache) it first. That way capability flags are available
        even when only BLE responds, and the coordinator can gate the candidates by odometer.

        Which sources this polls depends on the mode: ``cloud`` reads cloud only, ``ble`` reads
        BLE only, and ``ble_cloud`` reads both with BLE first (so a tie prefers the local source).
        """
        await self.get_vehicle_control_config(vehicle_id)
        # A control just read state back: that is this cycle's state, so use it and skip a re-read
        # (avoids a needless BLE reconnect / cloud round-trip right after acting).
        fresh = self._take_fresh_blob()
        if fresh is not None:
            state = self._decode_fresh_blob(*fresh)
            if state is not None:
                return [state]
        mode = self._transport_mode
        if mode == TRANSPORT_CLOUD:
            order: tuple[str, ...] = ("cloud",)
        elif mode == TRANSPORT_BLE:
            order = ("ble",)
        else:  # ble_cloud: BLE first so a tie prefers the local source.
            order = ("ble", "cloud")
        candidates: list[dict[str, Any]] = []
        for source in order:
            state = (
                await self._ble_state_candidate(vehicle_id)
                if source == "ble"
                else await self._cloud_state_candidate(vehicle_id)
            )
            if state is not None:
                candidates.append(state)
        return candidates
