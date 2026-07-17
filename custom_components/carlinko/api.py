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
RAW_TEST_BYTES: tuple[int, ...] = ()

# High/low byte pairs combined into a single 16-bit diagnostic value each, exposed as
# raw_word{hi}_{lo} — see decode_blob() for the hypothesis behind each pair.
RAW_WORD_PAIRS: tuple[tuple[int, int], ...] = ()

# byte 56: charging-connector/mode enum, confirmed against the vendor app's own readings.
CHARGING_CONNECTOR_STATES: dict[int, str] = {0: "disconnected", 1: "ac_slow", 2: "connected_idle", 16: "dc_fast"}

# byte 57: charging status enum, confirmed against the vendor app's own readings AND two live
# charging sessions — the reliable `charging` boolean is `byte57 != idle` (any in-progress,
# completed, canceled, hot-limited, or stopping state), not byte 58 (which is just the high
# byte of the remaining-time word at bytes 58:59, see below).
CHARGING_STATUSES: dict[int, str] = {
    0: "idle",
    1: "charging",
    2: "charge_complete",
    3: "charge_canceled",
    4: "hot_charging",
    5: "stop_charging",
}

# bytes 58:59 combined form a 16-bit "charging remaining time (minutes)" field; this sentinel
# (byte58==3, byte59==255) means N/A / not charging.
CHARGING_REMAINING_SENTINEL = 0x3FF


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
    d["door_front_left"] = bool(doors & 0x01)
    d["door_front_right"] = bool(doors & 0x02)
    d["door_rear_left"] = bool(doors & 0x04)
    d["door_rear_right"] = bool(doors & 0x08)
    d["lock_unlocked"] = bool(b[3])
    d["trunk_open"] = bool(b[4])
    d["ignition_on"] = bool(b[5])
    # byte 6: unused, always 0x00 across every capture
    # byte 7: unused, always 0x00 across every capture
    windows = b[8]
    d["window_front_left"] = bool((windows >> 6) & 0b11)
    d["window_front_right"] = bool((windows >> 4) & 0b11)
    d["window_rear_left"] = bool((windows >> 2) & 0b11)
    d["window_rear_right"] = bool(windows & 0b11)
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
    d["ac_on"] = bool(b[23])
    # byte 24: unused, varies — identical to byte 31 in every capture
    # byte 25: unused, always 0x02 across every capture
    # byte 26: unused, always 0x00 across every capture
    # byte 27: unused, always 0x00 across every capture
    d["battery_pct"] = b[28]
    d["battery_range_km"] = int.from_bytes(b[29:31], "big")
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
    d["charging_connector"] = CHARGING_CONNECTOR_STATES.get(b[56], "disconnected")
    d["charging_status"] = CHARGING_STATUSES.get(b[57], "idle")
    charging = d["charging_status"] != "idle"
    d["charging"] = charging
    charging_remaining_raw = (b[58] << 8) | b[59]
    is_remaining_na = charging_remaining_raw == CHARGING_REMAINING_SENTINEL
    d["charging_remaining_min"] = None if is_remaining_na else charging_remaining_raw
    # byte 60: unused, always 0x00 across every capture
    # byte 61: unused, always 0x00 across every capture
    power_kw = round(((b[62] << 8) | b[63]) * 0.1, 1)
    d["power_kw"] = power_kw
    d["charge_power_kw"] = power_kw if charging else 0.0
    d["regen_power_kw"] = power_kw if not charging else 0.0
    # byte 64: unused, always 0x00 across every capture
    # byte 65: unused, always 0x00 across every capture
    # byte 66: unused, always 0x00 across every capture
    # byte 67: unused, always 0xFF across every capture
    d["wltp_range_km"] = int.from_bytes(b[68:70], "big")
    d["fuel_range_km"] = int.from_bytes(b[70:72], "big")
    # byte 72: unused, always 0x02 across every capture
    return d
