"""Async CarLinko client: login (HMAC request signing) + REST telemetry polling.

Ported from tools/auth.py in the parent j5-ev-dashboard project (requests, sync) to
aiohttp (async, for Home Assistant's event loop). Telemetry reads use plain signed GETs
(`/user/vehicle/isOnline/{id}`, `/user/vehicle/state/{id}`) rather than the realtime
WebSocket — confirmed to return the identical status blob, see docs/api-map.md in the
parent project. The WebSocket is only needed for remote control, which this integration
doesn't implement.
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
    """Could not reach CarLinko."""


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
    """Talks to a single CarLinko account's REST API."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str, region: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._region = region
        self.token: str | None = None

    @property
    def api_base(self) -> str:
        return f"https://cqr-api-{self._region}.hzhjcl.com"

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

    async def _signed_get(self, path: str, _retried: bool = False) -> dict[str, Any]:
        """GET a token-authed endpoint and return the decoded `{"data":...,"code":...}` envelope.

        Re-logs in once and retries if the token was rejected (e.g. expired).
        """
        if not self.token:
            await self.login()
        headers = _headers_for({}, token=self.token)
        try:
            async with self._session.get(
                f"{self.api_base}{path}", headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise CarLinkoConnectionError(str(err)) from err
        try:
            data = json.loads(text)
        except json.JSONDecodeError as err:
            raise CarLinkoConnectionError(f"non-JSON response from {self.api_base}{path}: {text[:200]!r}") from err

        if str(data.get("code")) != "0000":
            if _retried:
                raise CarLinkoAuthError(data.get("msg") or f"request to {path} failed: {data}")
            await self.login()
            return await self._signed_get(path, _retried=True)
        return data

    async def get_vehicles(self) -> list[VehicleInfo]:
        """List vehicles on this account (used by config_flow to auto-detect the car)."""
        data = await self._signed_get("/user/vehicle")
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

    async def poll_telemetry(self, vehicle_id: str) -> dict[str, Any] | None:
        """Poll the vehicle status blob via plain signed GETs (no WebSocket needed for reads).

        Returns None if the car is reported offline.
        """
        online = await self._signed_get(f"/user/vehicle/isOnline/{vehicle_id}")
        if not online.get("data"):
            return None
        state = await self._signed_get(f"/user/vehicle/state/{vehicle_id}")
        blob = state.get("data")
        if not isinstance(blob, str):
            return None
        return decode_blob(blob)


# Suspect/unconfirmed bytes surfaced as raw diagnostic sensors so hypothesis testing can
# happen live in HA instead of only in the parent project's docs/api-map.md notes.
RAW_TEST_BYTES: tuple[int, ...] = (56, 57, 58, 59, 63)

# High/low byte pairs combined into a single 16-bit diagnostic value each, exposed as
# raw_word{hi}_{lo} — see decode_blob() for the hypothesis behind each pair.
RAW_WORD_PAIRS: tuple[tuple[int, int], ...] = ((68, 69), (70, 71))


def _psi(x: int) -> float | None:
    return None if x == 0xFF else round(x * 1.373 * 0.145, 1)


def _tyre_temp(x: int) -> int | None:
    # Confirmed against the app's own display: it truncates, not rounds (16.6 -> 16).
    return None if x == 0xFF else int(x * 0.65 - 40)


def decode_blob(hexstr: str) -> dict[str, Any]:
    """Decode the vehicle status blob returned by `/user/vehicle/state/{id}`.

    Byte map calibrated on a Jaecoo J5 EV and an Omoda E5.
    """
    b = bytes.fromhex(hexstr)
    d: dict[str, Any] = {"raw": hexstr}
    if len(b) < 73:  # confirmed length across every capture
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
    d["ignition_on"] = bool(b[5])
    # byte 6: unused, always 0x00 across every capture
    # byte 7: unused, always 0x00 across every capture
    windows = b[8]
    d["window_driver"] = bool((windows >> 6) & 0b11)
    d["window_passenger"] = bool((windows >> 4) & 0b11)
    d["window_rear_driver"] = bool((windows >> 2) & 0b11)
    d["window_rear_passenger"] = bool(windows & 0b11)
    d["sunroof_open"] = bool(b[9])
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
    # byte 24: unused, varies — identical to byte 31 in every capture
    # byte 25: unused, always 0x02 across every capture
    # byte 26: unused, always 0x00 across every capture
    # byte 27: unused, always 0x00 across every capture
    d["battery_pct"] = b[28]
    d["range_km"] = int.from_bytes(b[29:31], "big")
    # byte 31: unused, varies — identical to byte 24 in every capture
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
    d["raw_byte56"] = b[56]  # unconfirmed: charge cable connected (0=unplugged, 1=plugged in)
    d["raw_byte57"] = b[57]  # unconfirmed: looks like charge port / EVSE handshake state
    d["raw_byte58"] = b[58]  # confirmed: charging flag (2=charging, 3=not) — gates charge/regen below
    d["raw_byte59"] = b[59]  # unconfirmed: charge-power-gated counter, still unsolved (not a steady countdown)
    # byte 60: unused, always 0x00 across every capture
    # byte 61: unused, always 0x00 across every capture
    # byte 62: unused, always 0x00 across every capture
    power_kw = round(b[63] * 0.1, 1)
    d["raw_byte63"] = b[63]  # confirmed: power (kW, x0.1) — see charge/regen split below
    d["charge_power_kw"] = power_kw if b[58] == 2 else 0.0
    d["regen_power_kw"] = power_kw if b[58] == 3 else 0.0
    # byte 64: unused, always 0x00 across every capture
    # byte 65: unused, always 0x00 across every capture
    # byte 66: unused, always 0x00 across every capture
    # byte 67: unused, always 0xFF across every capture
    d["raw_word68_69"] = int.from_bytes(b[68:70], "big")
    # unconfirmed: trip energy used — decreases monotonically while driving,
    # holds steady when parked, ticks up briefly on hard regen
    d["raw_word70_71"] = int.from_bytes(b[70:72], "big")
    # unconfirmed: possible trip range — mirrors range exactly in every sample so far
    # byte 72: unused, always 0x02 across every capture
    return d
