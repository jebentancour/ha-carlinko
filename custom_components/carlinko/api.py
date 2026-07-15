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
    brand: str
    plate: str
    img_front: str
    img_side: str
    img_top: str


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
        payload = data.get("data")
        token = payload if isinstance(payload, str) else (payload or {}).get("token")
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
                )
            )
        return vehicles

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


# Suspect/unconfirmed bytes surfaced as raw diagnostic sensors so hypothesis testing can
# happen live in HA instead of only in the parent project's docs/api-map.md notes.
RAW_TEST_BYTES: tuple[int, ...] = (5, 57, 58, 59, 63, 68, 69, 70, 71)


def _psi(x: int) -> float | None:
    return None if x == 0xFF else round(x * 1.373 * 0.145, 1)


def _tyre_temp(x: int) -> int | None:
    # Confirmed against the app's own display: it truncates, not rounds (16.6 -> 16).
    return None if x == 0xFF else int(x * 0.65 - 40)


def decode_blob(hexstr: str) -> dict[str, Any]:
    """Decode the action:6 status blob.

    Byte map calibrated on a Jaecoo J5 EV, confirmed bit-for-bit on an Omoda E5. Byte 2 is
    a 4-bit door mask, byte 3 the lock state, byte 4 the trunk, byte 8 the windows (2 bits
    each, collapsed to open/closed — the "half open" bit value isn't surfaced separately),
    byte 9 the sunroof (0=closed, nonzero=open/vented). Byte 63 is power (kW, ×0.1); byte 58
    (1=charging, 3=not) splits it into charge_power_kw / regen_power_kw. Bytes 5, 57, 58, 59,
    63, 68, 69, 70 and 71 are also exposed unscaled as raw_byteN diagnostic sensors for
    hypotheses still being tested — see docs/api-map.md in the parent project for the rest
    of the blob.
    """
    b = bytes.fromhex(hexstr)
    d: dict[str, Any] = {"raw": hexstr}
    if len(b) < 73:  # confirmed length across every real capture (parent project's logs)
        return d

    # byte 0: unused, always 0x77 across every capture
    # byte 1: unused, always 0x00 across every capture
    doors = b[2]
    d["door_driver"] = bool(doors & 0x01)
    d["door_passenger"] = bool(doors & 0x02)
    d["door_rear_driver"] = bool(doors & 0x04)
    d["door_rear_passenger"] = bool(doors & 0x08)
    d["lock_unlocked"] = bool(b[3])
    d["trunk_open"] = bool(b[4])
    d["raw_byte5"] = b[5]  # suspected: LV/HV system state (0=inactive, 1=accessories, 2=motor/HV on)
    # byte 6: unused, always 0x00 across every capture
    # byte 7: unused, always 0x00 across every capture
    windows = b[8]
    d["window_driver"] = bool((windows >> 6) & 0b11)
    d["window_passenger"] = bool((windows >> 4) & 0b11)
    d["window_rear_driver"] = bool((windows >> 2) & 0b11)
    d["window_rear_passenger"] = bool(windows & 0b11)
    d["sunroof_open"] = b[9] != 0
    # byte 10: unused, always 0xFF across every capture
    # byte 11: unused, always 0x7F across every capture
    d["volt12"] = round(int.from_bytes(b[12:14], "big") * 0.01, 2)
    d["speed_kmh"] = round(int.from_bytes(b[14:16], "big") / 16.0, 1)
    # byte 16: unused, always 0x00 across every capture
    # byte 17: unused, always 0x00 across every capture
    d["odometer_km"] = int.from_bytes(b[18:21], "big")
    # byte 21: unused, always 0x00 across every capture
    # byte 22: unused, always 0x01 across every capture
    # byte 23: unused, varies (0/1)
    # byte 24: unused, varies — identical to byte 31 in every capture (mirrored)
    # byte 25: unused, always 0x02 across every capture
    # byte 26: unused, always 0x00 across every capture
    # byte 27: unused, always 0x00 across every capture
    d["battery_pct"] = b[28]
    d["range_km"] = int.from_bytes(b[29:31], "big")
    # byte 31: unused, varies — identical to byte 24 in every capture (mirrored)
    # byte 32: unused, always 0x00 across every capture
    # byte 33: unused, always 0x00 across every capture
    # byte 34: unused, always 0x00 across every capture
    # byte 35: unused, always 0x00 across every capture
    # byte 36: unused, always 0x00 across every capture
    # byte 37: unused, always 0x00 across every capture
    # byte 38: unused, always 0x00 across every capture
    # byte 39: unused, always 0x00 across every capture
    # byte 40: unused, always 0x00 across every capture
    # byte 41: unused, always 0x00 across every capture
    # byte 42: unused, always 0x00 across every capture
    # byte 43: unused, always 0x00 across every capture
    tp, tt = b[44:48], b[48:52]
    d["tyre_psi"] = [_psi(x) for x in tp]
    d["tyre_temp_c"] = [_tyre_temp(x) for x in tt]
    # byte 52: unused, always 0x00 across every capture
    # byte 53: unused, always 0x00 across every capture
    # byte 54: unused, always 0x00 across every capture
    d["consumption_kwh_100km"] = round(b[55] * 0.1, 1)
    # byte 56: unused, varies (0/1)
    d["raw_byte57"] = b[57]  # suspected: charge port/EVSE state (0=idle, 1=charging, 5=connect/disconnect)
    d["raw_byte58"] = b[58]  # confirmed: charging flag (1=charging, 3=not) — gates charge/regen below
    d["raw_byte59"] = b[59]  # suspected: charge-power-gated counter, still unsolved (not a steady countdown)
    # byte 60: unused, always 0x00 across every capture
    # byte 61: unused, always 0x00 across every capture
    # byte 62: unused, always 0x00 across every capture
    power_kw = round(b[63] * 0.1, 1)
    d["raw_byte63"] = b[63]  # confirmed: power (kW, x0.1) — see charge/regen split below
    d["charge_power_kw"] = power_kw if b[58] == 1 else 0.0
    d["regen_power_kw"] = power_kw if b[58] == 3 else 0.0
    # byte 64: unused, always 0x00 across every capture
    # byte 65: unused, always 0x00 across every capture
    # byte 66: unused, always 0x00 across every capture
    # byte 67: unused, always 0xFF across every capture
    d["raw_byte68"] = b[68]  # suspected: possible trip counter, unit unconfirmed — resets to 0 with byte 69 via the dash trip reset
    d["raw_byte69"] = b[69]  # suspected: possible trip energy counter, ~x0.1 kWh/unit — resets to 0 with byte 68 via the dash trip reset
    d["raw_byte70"] = b[70]  # suspected: possible trip counter, unit unconfirmed — always 0 so far, no calibration data yet
    d["raw_byte71"] = b[71]  # suspected: possible trip counter, in km like range_km — but mirrors byte 30 (range) exactly every time so far, may be redundant rather than a real trip field
    # byte 72: unused, always 0x02 across every capture
    return d
