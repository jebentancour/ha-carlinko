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

from .const import APP_LOGIN_BODY, DEFAULT_NOTICE_CONFIG_INTERVAL, SIGN_KEY, USER_AGENT


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
    trunk: bool = False
    find: bool = False
    charging_management: bool = False
    scheduled_charging: bool = False
    scheduled_travel: bool = False
    steering_wheel_heater: bool = False
    front_windshield_heater: bool = False
    charging_power: bool = False
    ac_switch: bool = False
    ac_set_temperature: bool = False
    ac_rapid_cool: bool = False
    ac_rapid_heat: bool = False
    ac_defog: bool = False
    ac_air_purification: bool = False
    ac_driver_vent: bool = False
    ac_assistant_vent: bool = False
    ac_driver_heater: bool = False
    ac_assistant_heater: bool = False
    ac_rear_heater: bool = False
    ac_high_low_gear: bool = False
    ac_set_duration: bool = False


@dataclass(frozen=True)
class VehicleControlConfig:
    """Per-model constants CarLinko publishes on `/user/vehicle` -> vehicleControlConfig."""

    tpms_scale: float = DEFAULT_TPMS_SCALE
    tire_pressure_invalid: frozenset[int] = DEFAULT_TIRE_INVALID
    tire_temp_invalid: frozenset[int] = DEFAULT_TIRE_INVALID
    charging_remaining_invalid: frozenset[int] = DEFAULT_CHARGING_REMAINING_INVALID
    is_phev: bool = False
    has_engine: bool = False
    has_fuel_consumption: bool = False
    has_power_consumption: bool = False
    trunk_type: int | None = None
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
    is_phev = has_fuel_consumption and has_power_consumption
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
        trunk=bool(cfg.get("Trunk")),
        find=bool(cfg.get("Search")),
        charging_management=bool(cfg.get("ChargingManagement")),
        scheduled_charging=bool(cfg.get("ScheduledCharging")),
        scheduled_travel=bool(cfg.get("ScheduledTravel")),
        steering_wheel_heater=bool(cfg.get("SteeringWheelHeater")),
        front_windshield_heater=bool(cfg.get("FrontWindshieldHeater")),
        charging_power=bool(cfg.get("chargingPower")),
        ac_switch=bool(ac.get("Switch")),
        ac_set_temperature=bool(ac.get("SetTemperature")),
        ac_rapid_cool=bool(ac.get("RapidCool")),
        ac_rapid_heat=bool(ac.get("RapidHeat")),
        ac_defog=bool(ac.get("Defogging")),
        ac_air_purification=bool(ac.get("AirPurification")),
        ac_driver_vent=bool(ac.get("DriverVent")),
        ac_assistant_vent=bool(ac.get("AssistantVent")),
        ac_driver_heater=bool(ac.get("DriverHeater")),
        ac_assistant_heater=bool(ac.get("AssistantHeater")),
        ac_rear_heater=bool(ac.get("RearHeater")),
        ac_high_low_gear=bool(ac.get("HighLowGear")),
        ac_set_duration=bool(ac.get("SetDuration")),
    )

    return VehicleControlConfig(
        tpms_scale=tpms_scale,
        tire_pressure_invalid=tire_pressure_invalid,
        tire_temp_invalid=tire_temp_invalid,
        charging_remaining_invalid=charging_remaining_invalid,
        is_phev=is_phev,
        has_engine=has_engine,
        has_fuel_consumption=has_fuel_consumption,
        has_power_consumption=has_power_consumption,
        trunk_type=cfg.get("TrunkType"),
        ac_temp_min=ac.get("SetTemperatureMin"),
        ac_temp_max=ac.get("SetTemperatureMax"),
        ac_temp_step=ac.get("TemperatureStepValue"),
        capabilities=capabilities,
    )


class CarLinkoClient:
    """Talks to a single CarLinko account's REST API.

    Endpoints are polled on different cadences depending on how often each one actually
    changes, fastest first: `isOnline` / `state` (telemetry, every poll) > `terminalNoticeConfig`
    (schedules/notifications, cached with a TTL — see `_get_notice_config`) >
    `vehicleControlConfig` (per-model constants, fetched once and cached forever).
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        region: str,
        notice_config_interval: int = DEFAULT_NOTICE_CONFIG_INTERVAL,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._region = region
        self._notice_config_ttl = notice_config_interval
        self.token: str | None = None
        self._control_config: VehicleControlConfig | None = None
        self._notice_config: dict[str, Any] | None = None
        self._notice_config_fetched_monotonic: float | None = None

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

    # ---- /user/device/manage/terminalNoticeConfig/{id} — schedules/notifications ----

    async def _get_notice_config(self, vehicle_id: str) -> dict[str, Any]:
        """Return the decoded notice config, refetching only once `self._notice_config_ttl`
        seconds have elapsed since the last successful fetch (user-configurable, see options flow).

        A failed refetch keeps serving the last known-good value instead of failing the whole
        poll, since this data changes far less often than the telemetry blob it's merged with.
        """
        now = time.monotonic()
        fresh = (
            self._notice_config is not None
            and self._notice_config_fetched_monotonic is not None
            and now - self._notice_config_fetched_monotonic < self._notice_config_ttl
        )
        if fresh:
            return self._notice_config

        try:
            notice = await self._signed_get(f"/user/device/manage/terminalNoticeConfig/{vehicle_id}")
        except (CarLinkoAuthError, CarLinkoConnectionError):
            if self._notice_config is not None:
                return self._notice_config
            raise

        self._notice_config = decode_notice_config(notice.get("data"))
        self._notice_config_fetched_monotonic = now
        return self._notice_config

    # ---- combined poll, one update cycle ----

    async def poll_telemetry(self, vehicle_id: str) -> dict[str, Any] | None:
        """Poll one update cycle's worth of vehicle state: online flag, telemetry (+ per-model
        config) and notice config, each fetched and decoded by its own section above.

        Returns None if the car is reported offline.
        """
        if not await self._fetch_online(vehicle_id):
            return None
        data = await self._get_state(vehicle_id)
        if data is None:
            return None
        data.update(await self._get_notice_config(vehicle_id))
        return data

RAW_TEST_BYTES: tuple[int, ...] = ()
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
    d["fuel_pct"] = b[21]
    # byte 22: unused, always 0x01 across every capture
    d["ac_on"] = bool(b[23])
    d["ac_temp_c"] = b[24]
    # byte 25: unused, always 0x02 across every capture
    # byte 26: unused, varies (0/1)
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
    # byte 67: unused, varies (0x00/0xFF)
    d["wltp_range_km"] = int.from_bytes(b[68:70], "big")
    d["range_km"] = int.from_bytes(b[70:72], "big")
    # byte 72: unused, always 0x02 across every capture

    return d


def decode_control_config(control_config: VehicleControlConfig | None = None) -> dict[str, Any]:
    """Expose `vehicleControlConfig` as flat entity data: powertrain, per-model constants and
    remote-control capability flags. Not telemetry — none of this comes from the status blob.
    """
    cfg = control_config or VehicleControlConfig()
    d: dict[str, Any] = {
        "powertrain": "phev" if cfg.is_phev else "bev",
        "has_engine": cfg.has_engine,
        "has_fuel_consumption": cfg.has_fuel_consumption,
        "has_power_consumption": cfg.has_power_consumption,
        "trunk_type": cfg.trunk_type,
        "ac_temp_min": cfg.ac_temp_min,
        "ac_temp_max": cfg.ac_temp_max,
        "ac_temp_step": cfg.ac_temp_step,
    }
    for name, value in dataclasses.asdict(cfg.capabilities).items():
        d[f"control_{name}"] = value
    return d


# Notice-config field order confirmed live 2026-08-14: marking Thursday-only in the app's
# trip-schedule screen produced week=[false,false,false,true,false,false,false] (index 3).
WEEKDAY_LABELS: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

def _parse_json_field(raw: Any) -> dict[str, Any]:
    """`extra`/`batterySchedule` are JSON *strings* nested inside the outer JSON response."""
    if not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _format_hhmm(hour: Any, minute: Any) -> str | None:
    try:
        return f"{int(hour):02d}:{int(minute):02d}"
    except (TypeError, ValueError):
        return None


def _format_week_days(week: Any) -> tuple[str | None, list[str] | None]:
    """Return a fixed, translatable state (none/all/custom) plus the active day labels
    (only set for "custom") as a separate attribute — the day combination itself is open-ended
    (2**7 possibilities) and can't be represented as a translatable HA enum state.
    """
    if not isinstance(week, list) or len(week) != 7:
        return None, None
    days = [bool(x) for x in week]
    if not any(days):
        return "none", None
    if all(days):
        return "all", None
    active = [label for label, on in zip(WEEKDAY_LABELS, days) if on]
    return "custom", active


def decode_notice_config(raw: Any) -> dict[str, Any]:
    """Decode `/user/device/manage/terminalNoticeConfig/{id}` — trip schedule and charge
    schedule preferences.

    A separate REST config resource, not part of the telemetry blob (confirmed 2026-08-14:
    toggling these in the app never moves a byte in `decode_blob`'s output).
    """
    cfg = raw if isinstance(raw, dict) else {}
    d: dict[str, Any] = {}

    # Viaje programado (scheduled trip / pre-conditioning). `startupAppointment` confirmed
    # live as the real enable flag (not just a notification toggle despite sitting among
    # them): toggling it in the app flips only this field, nothing else. "One-time" vs
    # "recurring" has no dedicated flag — the app infers it from whether any `week` day is set.
    trip = _parse_json_field(cfg.get("extra"))
    d["trip_schedule_enabled"] = bool(cfg.get("startupAppointment"))
    d["trip_schedule_time"] = _format_hhmm(trip.get("hour"), trip.get("minute"))
    d["trip_schedule_days"], d["trip_schedule_active_days"] = _format_week_days(trip.get("week"))

    # Carga programada.
    charge = _parse_json_field(cfg.get("batterySchedule"))
    d["charge_schedule_enabled"] = bool(charge.get("enabled"))
    d["charge_schedule_time"] = _format_hhmm(charge.get("hour"), charge.get("minute"))
    d["charge_schedule_duration_h"] = charge.get("duration")
    d["charge_schedule_days"], d["charge_schedule_active_days"] = _format_week_days(charge.get("week"))

    return d
