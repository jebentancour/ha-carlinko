"""Async CarLinko client: login (HMAC request signing) + REST telemetry polling.

Telemetry reads use plain signed GETs (`/user/vehicle/isOnline/{id}`, `/user/vehicle/state/{id}`).
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import (
    APP_LOGIN_BODY,
    CMD_AC_OFF,
    CMD_AC_ON,
    CMD_AC_SET_TEMPERATURE_PREFIX,
    CMD_DEFOG_FRONT_OFF,
    CMD_DEFOG_FRONT_ON,
    CMD_FIND_CAR,
    CMD_LIFTGATE_CLOSE,
    CMD_LIFTGATE_OPEN,
    CMD_LOCK,
    CMD_QUICK_COOL_OFF,
    CMD_QUICK_COOL_ON,
    CMD_QUICK_HEAT_OFF,
    CMD_QUICK_HEAT_ON,
    CMD_SEAT_HEAT_LEFT,
    CMD_SEAT_HEAT_RIGHT,
    CMD_SEAT_VENT_LEFT,
    CMD_SEAT_VENT_RIGHT,
    CMD_STOP_CHARGING,
    CMD_SUNROOF_CLOSE,
    CMD_SUNROOF_OPEN,
    CMD_SUNROOF_TILT,
    CMD_UNLOCK,
    CMD_WINDOWS_CLOSE,
    CMD_WINDOWS_OPEN,
    CMD_WINDOWS_VENT,
    SIGN_KEY,
    USER_AGENT,
)


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


DEFAULT_TPMS_SCALE = 1.373
DEFAULT_TIRE_INVALID: frozenset[int] = frozenset({0xFF})
DEFAULT_CHARGING_REMAINING_INVALID: frozenset[int] = frozenset({0x3FE, 0x3FF, 0x7FE, 0x7FF})


@dataclass(frozen=True)
class ControlCapabilities:
    """What this car can be told to do, straight from vehicleControlConfig."""

    lock: bool = False
    windows_open: bool = False
    windows_close: bool = False
    windows_vent: bool = False
    sunroof: bool = False
    sunroof_tilt: bool = False
    liftgate: bool = False
    find: bool = False
    charging: bool = False
    ac_switch: bool = False
    ac_set_temperature: bool = False
    ac_rapid_cool: bool = False
    ac_rapid_heat: bool = False
    ac_defog: bool = False
    ac_driver_vent: bool = False
    ac_assistant_vent: bool = False
    ac_driver_heater: bool = False
    ac_assistant_heater: bool = False
    ac_set_duration: bool = False


@dataclass(frozen=True)
class VehicleControlConfig:
    """Per-model constants CarLinko publishes on `/user/vehicle` -> vehicleControlConfig."""

    tpms_scale: float = DEFAULT_TPMS_SCALE
    tire_pressure_invalid: frozenset[int] = DEFAULT_TIRE_INVALID
    tire_temp_invalid: frozenset[int] = DEFAULT_TIRE_INVALID
    charging_remaining_invalid: frozenset[int] = DEFAULT_CHARGING_REMAINING_INVALID
    has_engine: bool = False
    has_fuel_consumption: bool = False
    has_power_consumption: bool = False
    ac_temp_min: float | None = None
    ac_temp_max: float | None = None
    ac_temp_step: float | None = None
    capabilities: ControlCapabilities = ControlCapabilities()


def _hex_set(values: Any) -> frozenset[int] | None:
    if not isinstance(values, list) or not values:
        return None
    try:
        return frozenset(int(str(v), 16) for v in values)
    except (TypeError, ValueError):
        return None


def _parse_vehicle_control_config(raw: Any) -> VehicleControlConfig:
    cfg = raw
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg or "{}")
        except json.JSONDecodeError:
            cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}

    formula = str(cfg.get("appKpaFormula") or cfg.get("webTirePressureFormula") or "")
    m = re.search(r"data\s*\*\s*([0-9]*\.?[0-9]+)", formula)
    tpms_scale = float(m.group(1)) if m else DEFAULT_TPMS_SCALE

    tire_pressure_invalid = _hex_set(cfg.get("tirePressureInvalid")) or DEFAULT_TIRE_INVALID
    tire_temp_invalid = _hex_set(cfg.get("tireTempInvalid")) or DEFAULT_TIRE_INVALID
    charging_remaining_invalid = _hex_set(cfg.get("chargingTimeInvalidValue")) or DEFAULT_CHARGING_REMAINING_INVALID

    has_fuel_consumption = bool(cfg.get("fuelConsumption"))
    has_power_consumption = bool(cfg.get("powerConsumption"))
    has_engine = bool(cfg.get("Engine"))

    ac = cfg.get("A/C") or {}
    capabilities = ControlCapabilities(
        lock=bool(cfg.get("Lock")),
        windows_open=bool(cfg.get("WindowsOpen")),
        windows_close=bool(cfg.get("WindowsClose")),
        windows_vent=bool(cfg.get("WindowsVent")),
        sunroof=bool(cfg.get("Sunroof")),
        sunroof_tilt=bool(cfg.get("SunroofTilting")),
        liftgate=bool(cfg.get("PowerLiftgate")),
        find=bool(cfg.get("Search")),
        charging=bool(cfg.get("ChargingManagement")),
        ac_switch=bool(ac.get("Switch")),
        ac_set_temperature=bool(ac.get("SetTemperature")),
        ac_rapid_cool=bool(ac.get("RapidCool")),
        ac_rapid_heat=bool(ac.get("RapidHeat")),
        ac_defog=bool(ac.get("Defogging")),
        ac_driver_vent=bool(ac.get("DriverVent")),
        ac_assistant_vent=bool(ac.get("AssistantVent")),
        ac_driver_heater=bool(ac.get("DriverHeater")),
        ac_assistant_heater=bool(ac.get("AssistantHeater")),
        ac_set_duration=bool(ac.get("SetDuration")),
    )

    return VehicleControlConfig(
        tpms_scale=tpms_scale,
        tire_pressure_invalid=tire_pressure_invalid,
        tire_temp_invalid=tire_temp_invalid,
        charging_remaining_invalid=charging_remaining_invalid,
        has_engine=has_engine,
        has_fuel_consumption=has_fuel_consumption,
        has_power_consumption=has_power_consumption,
        ac_temp_min=ac.get("SetTemperatureMin"),
        ac_temp_max=ac.get("SetTemperatureMax"),
        ac_temp_step=ac.get("TemperatureStepValue"),
        capabilities=capabilities,
    )


class CarLinkoClient:
    """Talks to a single CarLinko account's REST API.

    Endpoints are polled on different cadences depending on how often each one actually
    changes, fastest first: `isOnline` / `state` (telemetry, every poll) >
    `vehicleControlConfig` (per-model constants, fetched once and cached forever).
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        region: str,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._region = region
        self.token: str | None = None
        self._control_config: VehicleControlConfig | None = None

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

    # ---- /user/vehicle/remoteControl — actuation commands ----

    async def _send_remote_command(self, vehicle_id: str, device_sn: str, opcode: str, timeout: int = 20) -> None:
        """POST a remote-control opcode. Raises on rejection.

        This only confirms CarLinko accepted the command for delivery to the car — the
        actuation result itself comes back over CarLinko's WebSocket, which this integration
        doesn't hold open, so there's no ack to wait on here.
        """
        if not self.token:
            await self.login()
        body = {"vehicleId": vehicle_id, "deviceSn": device_sn, "data": opcode, "timeOut": timeout}

        async def _post(token: str) -> dict[str, Any]:
            headers = _headers_for(body, token=token)
            headers["content-type"] = "application/json"
            try:
                async with self._session.post(
                    f"{self.api_base}/user/vehicle/remoteControl",
                    json=body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout + 8),
                ) as resp:
                    text = await resp.text()
            except aiohttp.ClientError as err:
                raise CarLinkoConnectionError(str(err)) from err
            try:
                return json.loads(text)
            except json.JSONDecodeError as err:
                raise CarLinkoConnectionError(f"non-JSON response from remoteControl: {text[:200]!r}") from err

        data = await _post(self.token)
        if str(data.get("code")) != "0000":
            data = await _post(await self.login())
            if str(data.get("code")) != "0000":
                raise CarLinkoConnectionError(data.get("msg") or f"remoteControl command rejected: {data}")

    async def stop_charging(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_STOP_CHARGING)

    async def find_car(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_FIND_CAR)

    async def lock(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_LOCK)

    async def unlock(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_UNLOCK)

    async def open_liftgate(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_LIFTGATE_OPEN)

    async def close_liftgate(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_LIFTGATE_CLOSE)

    async def open_sunroof(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_SUNROOF_OPEN)

    async def close_sunroof(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_SUNROOF_CLOSE)

    async def tilt_sunroof(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_SUNROOF_TILT)

    async def open_windows(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_WINDOWS_OPEN)

    async def close_windows(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_WINDOWS_CLOSE)

    async def vent_windows(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_WINDOWS_VENT)

    async def defrost_on(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_DEFOG_FRONT_ON)

    async def defrost_off(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_DEFOG_FRONT_OFF)

    async def set_seat_heat_left(self, vehicle_id: str, device_sn: str, level: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_SEAT_HEAT_LEFT[level])

    async def set_seat_heat_right(self, vehicle_id: str, device_sn: str, level: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_SEAT_HEAT_RIGHT[level])

    async def set_seat_vent_left(self, vehicle_id: str, device_sn: str, level: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_SEAT_VENT_LEFT[level])

    async def set_seat_vent_right(self, vehicle_id: str, device_sn: str, level: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_SEAT_VENT_RIGHT[level])

    async def quick_heat_on(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_QUICK_HEAT_ON)

    async def quick_heat_off(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_QUICK_HEAT_OFF)

    async def quick_cool_on(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_QUICK_COOL_ON)

    async def quick_cool_off(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_QUICK_COOL_OFF)

    async def ac_power_on(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_AC_ON)

    async def ac_power_off(self, vehicle_id: str, device_sn: str) -> None:
        await self._send_remote_command(vehicle_id, device_sn, CMD_AC_OFF)

    async def set_ac_temperature(self, vehicle_id: str, device_sn: str, target_temp_c: float) -> None:
        """Encode + send an A/C set-temperature command.

        The payload depends on this car's own temperature step (whole vs. half degree), which
        `vehicleControlConfig.A/C.TemperatureStepValue` publishes — cached on this client via
        `get_vehicle_control_config()`, called on every poll, so it's available by the time any
        entity can call this.
        """
        step = self._control_config.ac_temp_step if self._control_config else None
        raw = int(round(target_temp_c * 2)) | 0x80 if step == 0.5 else int(round(target_temp_c))
        opcode = f"{CMD_AC_SET_TEMPERATURE_PREFIX}{raw & 0xFF:02x}"
        await self._send_remote_command(vehicle_id, device_sn, opcode)

    # ---- /user/vehicle — vehicle list + per-model vehicleControlConfig ----

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

    async def get_vehicle_control_config(self, vehicle_id: str) -> VehicleControlConfig:
        """Fetch + cache vehicleControlConfig for this vehicle.

        It's a per-model constant CarLinko won't change under us, so one fetch per client
        lifetime (i.e. per HA config entry, since the client lives on the coordinator) is enough.
        """
        if self._control_config is not None:
            return self._control_config
        data = await self._signed_get("/user/vehicle")
        raw = data.get("data")
        items = raw if isinstance(raw, list) else ([raw] if raw else [])
        vehicle = next((v for v in items if str(v.get("vehicleId")) == str(vehicle_id)), None)
        self._control_config = _parse_vehicle_control_config((vehicle or {}).get("vehicleControlConfig"))
        return self._control_config

    # ---- /user/vehicle/isOnline/{id} ----

    async def _fetch_online(self, vehicle_id: str) -> bool:
        online = await self._signed_get(f"/user/vehicle/isOnline/{vehicle_id}")
        return bool(online.get("data"))

    # ---- /user/vehicle/state/{id} — telemetry blob ----

    async def _get_state(self, vehicle_id: str) -> dict[str, Any] | None:
        """Fetch + decode the telemetry blob, merged with the vehicleControlConfig facts
        (powertrain, capabilities) needed to interpret some of its bytes and describe this car.

        Returns None if the car didn't report a blob this poll.
        """
        state = await self._signed_get(f"/user/vehicle/state/{vehicle_id}")
        blob = state.get("data")
        if not isinstance(blob, str):
            return None
        control_config = await self.get_vehicle_control_config(vehicle_id)
        data = decode_blob(blob, control_config)
        data.update(decode_control_config(control_config))
        return data

    # ---- combined poll, one update cycle ----

    async def poll_telemetry(self, vehicle_id: str) -> dict[str, Any] | None:
        """Poll one update cycle's worth of vehicle state: online flag and telemetry (+
        per-model config), each fetched and decoded by its own section above.

        Returns None if the car is reported offline.
        """
        if not await self._fetch_online(vehicle_id):
            return None
        return await self._get_state(vehicle_id)

RAW_TEST_BYTES: tuple[int, ...] = (3, 5, 67)
RAW_WORD_PAIRS: tuple[tuple[int, int], ...] = ()

CHARGING_CONNECTOR_STATES: dict[int, str] = {0: "disconnected", 1: "ac_slow", 16: "dc_fast"}

CHARGING_STATUSES: dict[int, str] = {
    0: "idle",
    1: "charging",
    2: "charge_complete",
    3: "charge_canceled",
    4: "hot_charging",
    5: "stop_charging",
}

SEAT_LEVELS: dict[int, str] = {0: "off", 1: "low", 2: "medium", 3: "high"}

SUNROOF_STATES: dict[int, str] = {0x00: "closed", 0x08: "open", 0x0B: "tilted"}

WINDOW_STATES: dict[int, str] = {0b00: "closed", 0b01: "open", 0b10: "vent"}


def decode_blob(hexstr: str, control_config: VehicleControlConfig | None = None) -> dict[str, Any]:
    """Decode the vehicle status blob returned by `/user/vehicle/state/{id}`."""
    cfg = control_config or VehicleControlConfig()

    def _psi(x: int) -> float | None:
        return None if x in cfg.tire_pressure_invalid else round(x * cfg.tpms_scale * 0.145, 1)

    def _tyre_temp(x: int) -> int | None:
        # Confirmed against the app's own display: it truncates, not rounds (16.6 -> 16).
        return None if x in cfg.tire_temp_invalid else int(x * 0.65 - 40)

    def _charging_remaining(x: int) -> int | None:
        return None if x in cfg.charging_remaining_invalid else x

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
    d["raw_byte3"] = b[3]
    d["liftgate_open"] = bool(b[4])
    d["ignition_on"] = bool(b[5])
    d["raw_byte5"] = b[5]
    # byte 6: unused, always 0x00 across every capture
    # byte 7: unused, always 0x00 across every capture
    windows = b[8]
    d["window_front_left"] = WINDOW_STATES.get((windows >> 6) & 0b11, "open")
    d["window_front_right"] = WINDOW_STATES.get((windows >> 4) & 0b11, "open")
    d["window_rear_left"] = WINDOW_STATES.get((windows >> 2) & 0b11, "open")
    d["window_rear_right"] = WINDOW_STATES.get(windows & 0b11, "open")
    d["sunroof_state"] = SUNROOF_STATES.get(b[9], "open" if b[9] else "closed")
    # byte 10: unused, always 0xFF across every capture
    # byte 11: unused, always 0x7F across every capture
    d["volt12"] = round(int.from_bytes(b[12:14], "big") * 0.01, 2)
    d["speed_kmh"] = round(int.from_bytes(b[14:16], "big") / 16.0, 1)
    # byte 16: unused, always 0x00 across every capture
    # byte 17: unused, always 0x00 across every capture
    d["odometer_km"] = int.from_bytes(b[18:21], "big")
    d["fuel_pct"] = b[21]
    # byte 22: unused, always 0x01 across every capture
    d["ac_on"] = bool(b[23])
    d["ac_temp_c"] = b[24]
    # byte 25: unused, always 0x02 across every capture
    # byte 26: unused, varies (0x00/0x01)
    # byte 27: unused, always 0x00 across every capture
    d["battery_pct"] = b[28]
    d["battery_range_km"] = int.from_bytes(b[29:31], "big")
    # byte 31: unused, varies — identical to byte 24 (ac_temp_c) in every capture
    d["seat_heat_left"] = SEAT_LEVELS.get(b[32], "off")
    d["seat_heat_right"] = SEAT_LEVELS.get(b[33], "off")
    # byte 34: unused, always 0x00 across every capture
    # byte 35: unused, always 0x00 across every capture
    # byte 36: unused, always 0x00 across every capture
    d["seat_vent_left"] = SEAT_LEVELS.get(b[37], "off")
    d["seat_vent_right"] = SEAT_LEVELS.get(b[38], "off")
    # byte 39: unused, always 0x00 across every capture
    # byte 40: unused, always 0x00 across every capture
    # byte 41: unused, always 0x00 across every capture
    d["defrost_front"] = bool(b[42])
    # byte 43: unused, always 0x00 across every capture
    tp, tt = b[44:48], b[48:52]
    d["tyre_psi"] = [_psi(x) for x in tp]
    d["tyre_temp_c"] = [_tyre_temp(x) for x in tt]
    # byte 52: unused, always 0x00 across every capture
    d["fuel_l_100"] = round(b[53] * 0.1, 1)
    # byte 54: unknown meaning — reads 20 on every confirmed PHEV frame, 0 on every BEV frame
    d["consumption_kwh_100km"] = round(b[55] * 0.1, 1)
    d["charging_connector"] = CHARGING_CONNECTOR_STATES.get(b[56], "disconnected")
    d["charging_status"] = CHARGING_STATUSES.get(b[57], "idle")
    charging = d["charging_status"] != "idle"
    d["charging"] = charging
    d["charging_remaining_min"] = _charging_remaining((b[58] << 8) | b[59])
    # byte 60: unused, always 0x00 across every capture
    # byte 61: unused, always 0x00 across every capture
    power_kw = round(((b[62] << 8) | b[63]) * 0.1, 1)
    d["power_kw"] = power_kw
    d["charge_power_kw"] = power_kw if charging else 0.0
    d["regen_power_kw"] = power_kw if not charging else 0.0
    # byte 64: unused, always 0x00 across every capture
    # byte 65: unused, always 0x00 across every capture
    # byte 66: unused, always 0x00 across every capture
    # byte 67: unknown meaning — varies (0x00/0x02/0xFF)
    d["raw_byte67"] = b[67]
    d["wltp_range_km"] = int.from_bytes(b[68:70], "big")
    d["range_km"] = int.from_bytes(b[70:72], "big")
    # byte 72: unused, always 0x02 across every capture

    return d


def decode_control_config(control_config: VehicleControlConfig | None = None) -> dict[str, Any]:
    """Expose `vehicleControlConfig` as flat entity data: per-model constants and remote-control
    capability flags. Not telemetry — none of this comes from the status blob.
    """
    cfg = control_config or VehicleControlConfig()
    d: dict[str, Any] = {
        "has_engine": cfg.has_engine,
        "has_fuel_consumption": cfg.has_fuel_consumption,
        "has_power_consumption": cfg.has_power_consumption,
        "ac_temp_min": cfg.ac_temp_min,
        "ac_temp_max": cfg.ac_temp_max,
        "ac_temp_step": cfg.ac_temp_step,
    }
    for name, value in dataclasses.asdict(cfg.capabilities).items():
        d[f"control_{name}"] = value
    return d
