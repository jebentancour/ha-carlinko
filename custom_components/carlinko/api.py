"""Async CarLinko client: login (HMAC request signing) + realtime WebSocket telemetry.

Ported from tools/auth.py and tools/ws_client.py in the parent j5-ev-dashboard project
(requests/websocket-client, sync) to aiohttp (async, for Home Assistant's event loop).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import APP_LOGIN_BODY, SIGN_KEY, USER_AGENT


class CarLinkoAuthError(Exception):
    """Login/credentials rejected."""


class CarLinkoConnectionError(Exception):
    """Could not reach CarLinko (REST or WebSocket)."""


def _now_ms() -> str:
    return str(int(time.time() * 1000))


def _sign(params: dict[str, Any]) -> str:
    m = {k: ("" if v is None else str(v)) for k, v in params.items()}
    ordered = {k: m[k] for k in sorted(m.keys())}
    msg = json.dumps(ordered, separators=(",", ":"), ensure_ascii=False).encode()
    return base64.b64encode(hmac.new(SIGN_KEY, msg, hashlib.sha256).digest()).decode()


def _headers_for(params: dict[str, Any], token: str | None = None) -> dict[str, str]:
    ts = _now_ms()
    h = {
        "timestamp": ts,
        "signature": _sign({**params, "timestamp": ts}),
        "user-agent": USER_AGENT,
        "language": "en",
    }
    if token:
        h["token"] = token
    return h


@dataclass
class VehicleInfo:
    vehicle_id: str
    device_sn: str
    model: str
    vin: str
    plate: str


class CarLinkoClient:
    """Talks to a single CarLinko account's REST API + realtime WebSocket."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str, region: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._region = region
        self.token: str | None = None

    @property
    def api_base(self) -> str:
        return f"https://cqr-api-{self._region}.hzhjcl.com"

    @property
    def ws_url(self) -> str:
        return f"ws://wss-cqr-{self._region}.hzhjcl.com:4002/"

    async def login(self) -> str:
        """Log in with the stored account, return + cache the new session token."""
        body = {
            "account": self._email,
            "password": self._password,
            "dateTime": _now_ms(),
            **APP_LOGIN_BODY,
        }
        ts = _now_ms()
        headers = {
            "timestamp": ts,
            "signature": _sign({**body, "timestamp": ts}),
            "user-agent": USER_AGENT,
            "content-type": "application/json",
            "language": "en",
        }
        try:
            async with self._session.post(
                f"{self.api_base}/user/login", json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise CarLinkoConnectionError(str(err)) from err
        try:
            data = json.loads(text)
        except json.JSONDecodeError as err:
            raise CarLinkoConnectionError(f"non-JSON response from {self.api_base}: {text[:200]!r}") from err

        if str(data.get("code")) != "0000":
            raise CarLinkoAuthError(data.get("msg") or f"login failed: {data}")
        token = (data.get("data") or {}).get("token")
        if not token:
            raise CarLinkoAuthError(f"login ok but no token in response: {data}")
        self.token = token
        return token

    async def get_vehicles(self) -> list[VehicleInfo]:
        """List vehicles on this account (used by config_flow to auto-detect the car)."""
        if not self.token:
            await self.login()
        headers = _headers_for({}, token=self.token)
        try:
            async with self._session.get(
                f"{self.api_base}/user/vehicle", headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise CarLinkoConnectionError(str(err)) from err
        try:
            data = json.loads(text)
        except json.JSONDecodeError as err:
            raise CarLinkoConnectionError(f"non-JSON response from {self.api_base}: {text[:200]!r}") from err

        raw = data.get("data")
        items = raw if isinstance(raw, list) else ([raw] if raw else [])
        return [
            VehicleInfo(
                vehicle_id=str(v.get("vehicleId")),
                device_sn=str(v.get("deviceId") or ""),
                model=v.get("model") or "EV",
                vin=v.get("vin") or "",
                plate=v.get("licenseNumber") or "",
            )
            for v in items
            if v.get("vehicleId")
        ]

    async def poll_telemetry(self, vehicle_id: str, device_sn: str, _retried: bool = False) -> dict[str, Any] | None:
        """Open the realtime WebSocket, request the status blob, decode it.

        Returns None if the car is offline (no action:6 blob within the poll window).
        Auto-refreshes the token once (re-login) if the WS login is rejected.
        """
        if not self.token:
            await self.login()

        try:
            async with self._session.ws_connect(
                self.ws_url, headers={"User-Agent": USER_AGENT}, timeout=20, autoclose=True
            ) as ws:
                await ws.send_str(json.dumps({"action": 1, "data": {"token": self.token, "vehicleId": vehicle_id}}))
                login_msg = await ws.receive(timeout=10)
                login_reply = json.loads(login_msg.data)
                if str(login_reply.get("code")) != "0000":
                    if _retried:
                        raise CarLinkoAuthError(f"WS login rejected after refresh: {login_reply}")
                    await self.login()
                    return await self.poll_telemetry(vehicle_id, device_sn, _retried=True)

                await ws.send_str(json.dumps({"action": 6}))
                await ws.send_str(json.dumps({"action": 0, "data": {"sn": device_sn}}))

                blob: str | None = None
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        msg = await ws.receive(timeout=remaining)
                    except TimeoutError:
                        break
                    if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR):
                        break
                    if msg.type is not aiohttp.WSMsgType.TEXT:
                        continue
                    try:
                        j = json.loads(msg.data)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if j.get("action") == 6 and isinstance(j.get("data"), str):
                        blob = j["data"]
                        break
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise CarLinkoConnectionError(str(err)) from err

        if not blob:
            return None
        return decode_blob(blob)


# Suspect/unconfirmed bytes (see memory + tools/recon.py hypotheses) surfaced as raw
# diagnostic sensors so hypothesis testing can happen live in HA instead of only recon.py.
RAW_TEST_BYTES: tuple[int, ...] = (3, 5, 9, 57, 58, 59, 63, 69)


def _psi(x: int) -> float | None:
    return None if x == 0xFF else round(x * 1.373 * 0.145, 1)


def _tyre_temp(x: int) -> int | None:
    # Confirmed against the app's own display: it truncates, not rounds (16.6 -> 16).
    return None if x == 0xFF else int(x * 0.65 - 40)


def decode_blob(hexstr: str) -> dict[str, Any]:
    """Decode the action:6 status blob.

    Validated against a Jaecoo J5 EV, then bit-for-bit against an Omoda E5's own app
    display on 2026-07-14 (same CarLinko/Chery blob layout): battery, range, odometer,
    12V, speed, consumption, tyre PSI/temp. Doors + trunk confirmed the same day via a
    dedicated test session (open/close each door and the trunk one at a time, watch which
    byte moves) — byte 2 is a 4-bit door mask, byte 4 is the trunk (on this car the charge
    port is reached by opening the trunk, which is why it also fired during charge-port
    tests). Power (byte 63) confirmed the same day against a real charge session — matched
    the app's displayed "2.10 kW" exactly, twice, ~11 minutes apart. Byte 58 (3=not
    charging, 1=charging) disambiguates that same byte 63 reading: it also spikes from
    regen/braking while driving, not just while plugged in — so it's split into two
    sensors, charge_power_kw and regen_power_kw, based on byte 58. Bytes 3, 5, 9, 57, 58,
    59, 63 and 69 are also exposed as raw, unscaled diagnostic sensors (raw_byteN) for
    ongoing hypothesis testing in HA itself — see the byte-map notes in memory / the
    parent project's tools/recon.py for what each is suspected to mean. Everything else
    decoded here is confirmed; for exploring the rest of the blob, see tools/recon.py in
    the parent project.
    """
    b = bytes.fromhex(hexstr)
    d: dict[str, Any] = {"raw": hexstr}
    for n in RAW_TEST_BYTES:
        if len(b) > n:
            d[f"raw_byte{n}"] = b[n]
    if len(b) > 30:
        doors = b[2]
        d["door_driver"] = bool(doors & 0x01)
        d["door_passenger"] = bool(doors & 0x02)
        d["door_rear_driver"] = bool(doors & 0x04)
        d["door_rear_passenger"] = bool(doors & 0x08)
        d["trunk_open"] = bool(b[4])
        d["battery_pct"] = b[28]
        d["range_km"] = int.from_bytes(b[29:31], "big")
        d["odometer_km"] = int.from_bytes(b[18:21], "big")
        d["volt12"] = round(int.from_bytes(b[12:14], "big") * 0.01, 2)
        d["speed_kmh"] = round(int.from_bytes(b[14:16], "big") / 16.0, 1)
    if len(b) >= 56:
        d["consumption_kwh_100km"] = round(b[55] * 0.1, 1)
    if len(b) >= 64:
        power_kw = round(b[63] * 0.1, 1)
        is_charging = b[58] == 1
        d["charge_power_kw"] = power_kw if is_charging else 0.0
        d["regen_power_kw"] = power_kw if not is_charging else 0.0
    if len(b) >= 52:
        tp, tt = b[44:48], b[48:52]
        d["tyre_psi"] = [_psi(x) for x in tp]
        d["tyre_temp_c"] = [_tyre_temp(x) for x in tt]
    return d
