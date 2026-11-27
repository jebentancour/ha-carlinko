"""Decoder for the CarLinko vehicle status blob and the per-model config flattening.

The blob is identical whether it arrives from the cloud (`/user/vehicle/state`) or over BLE (the
``0x77`` status frame), so this module decodes bytes only — no Home Assistant, bleak or network. The
byte mapping is the authority for this integration and is deliberately kept as-is.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from .capabilities import VehicleControlConfig

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


# Sanity bounds used to reject a corrupt / misaligned telemetry frame before it reaches the
# sensors or the odometer freshness gate — a frame can pass the CRC and still be garbage.
_PLAUSIBLE_RANGES: tuple[tuple[str, float, float], ...] = (
    ("odometer_km", 0, 2_000_000),
    ("speed_kmh", 0, 320),
    ("volt12", 6, 20),
    ("battery_pct", 0, 100),
)


def is_plausible(data: dict[str, Any]) -> bool:
    """False if a decoded blob carries physically impossible values (a corrupt frame)."""
    for key, low, high in _PLAUSIBLE_RANGES:
        value = data.get(key)
        if value is not None and not (low <= value <= high):
            return False
    return True


def parse_fw_version(reply: bytes | None) -> str | None:
    """Decode a ``0x24`` firmware-version reply (``24 00 <ascii> 00``) into the version string."""
    if not reply or len(reply) < 3 or reply[0] != 0x24:
        return None
    body = reply[2:]
    end = body.find(0)
    if end != -1:
        body = body[:end]
    try:
        return body.decode("ascii").strip() or None
    except UnicodeDecodeError:
        return None


def decode_blob(hexstr: str, control_config: VehicleControlConfig | None = None) -> dict[str, Any]:
    """Decode the vehicle status blob returned by `/user/vehicle/state/{id}`."""
    cfg = control_config or VehicleControlConfig()

    def _psi(x: int) -> float | None:
        return None if x in cfg.tire_pressure_invalid else round(x * cfg.tpms_scale * 0.145, 1)

    def _tyre_temp(x: int) -> int | None:
        # Truncated, not rounded, to match the app.
        return None if x in cfg.tire_temp_invalid else int(x * 0.65 - 40)

    def _charging_remaining(x: int) -> int | None:
        return None if x in cfg.charging_remaining_invalid else x

    b = bytes.fromhex(hexstr)
    d: dict[str, Any] = {}
    if len(b) < 72:
        return d

    doors = b[2]
    d["door_front_left"] = bool(doors & 0x01)
    d["door_front_right"] = bool(doors & 0x02)
    d["door_rear_left"] = bool(doors & 0x04)
    d["door_rear_right"] = bool(doors & 0x08)
    d["lock_unlocked"] = bool(b[3])
    d["liftgate_open"] = bool(b[4])
    d["ignition_on"] = bool(b[5])
    windows = b[8]
    d["window_front_left"] = WINDOW_STATES.get((windows >> 6) & 0b11, "open")
    d["window_front_right"] = WINDOW_STATES.get((windows >> 4) & 0b11, "open")
    d["window_rear_left"] = WINDOW_STATES.get((windows >> 2) & 0b11, "open")
    d["window_rear_right"] = WINDOW_STATES.get(windows & 0b11, "open")
    d["sunroof_state"] = SUNROOF_STATES.get(b[9], "open" if b[9] else "closed")
    d["volt12"] = round(int.from_bytes(b[12:14], "big") * 0.01, 2)
    d["speed_kmh"] = round(int.from_bytes(b[14:16], "big") / 16.0, 1)
    d["engine_rpm"] = int.from_bytes(b[16:18], "big")
    d["odometer_km"] = int.from_bytes(b[18:21], "big")
    d["fuel_pct"] = b[21]
    d["ac_on"] = bool(b[23])
    d["ac_temp_c"] = b[24]
    d["ac_compressor"] = bool(b[26])
    d["battery_pct"] = b[28]
    d["battery_range_km"] = int.from_bytes(b[29:31], "big")
    d["seat_heat_left"] = SEAT_LEVELS.get(b[32], "off")
    d["seat_heat_right"] = SEAT_LEVELS.get(b[33], "off")
    d["seat_heat_rear_left"] = SEAT_LEVELS.get(b[34], "off")
    d["seat_heat_rear_right"] = SEAT_LEVELS.get(b[36], "off")
    d["seat_vent_left"] = SEAT_LEVELS.get(b[37], "off")
    d["seat_vent_right"] = SEAT_LEVELS.get(b[38], "off")
    d["seat_vent_rear_left"] = SEAT_LEVELS.get(b[39], "off")
    d["seat_vent_rear_right"] = SEAT_LEVELS.get(b[41], "off")
    d["defrost_front"] = bool(b[42])
    tp, tt = b[44:48], b[48:52]
    d["tyre_psi"] = [_psi(x) for x in tp]
    d["tyre_temp_c"] = [_tyre_temp(x) for x in tt]
    d["fuel_l_100"] = round(b[53] * 0.1, 1)
    consumption_mode = b[54] >> 4
    consumption_mag = ((b[54] & 0xF) << 8) | b[55]
    d["consumption_kwh_100km"] = round(
        consumption_mag * 0.1 - (100 if consumption_mode == 1 else 0), 1
    )
    d["charging_connector"] = CHARGING_CONNECTOR_STATES.get(b[56], "disconnected")
    d["charging_status"] = CHARGING_STATUSES.get(b[57], "idle")
    charging = d["charging_connector"] != "disconnected"
    d["charging"] = charging
    d["charging_remaining_min"] = _charging_remaining((b[58] << 8) | b[59])
    power_kw = round(((b[62] << 8) | b[63]) * 0.1, 1)
    d["power_kw"] = power_kw
    d["charge_power_kw"] = power_kw if charging else 0.0
    d["regen_power_kw"] = power_kw if not charging else 0.0
    d["windshield_heat"] = bool(b[64])
    d["steering_wheel_heat"] = bool(b[65])
    d["air_purifier"] = bool(b[66])
    d["wltp_range_km"] = int.from_bytes(b[68:70], "big")
    d["range_km"] = int.from_bytes(b[70:72], "big")
    if len(b) > 73:
        d["sunshade_open"] = bool(b[73])
    if len(b) > 74:
        d["rear_window_defog"] = bool(b[74])

    return d


def decode_control_config(control_config: VehicleControlConfig | None = None) -> dict[str, Any]:
    """Flatten vehicleControlConfig (per-model constants + capability flags) into entity data."""
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
