"""Vehicle metadata and per-model capabilities from CarLinko's `/user/vehicle` endpoint.

Pure data + parsing: no Home Assistant, bleak or network dependency.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

DEFAULT_TPMS_SCALE = 1.373
DEFAULT_TIRE_INVALID: frozenset[int] = frozenset({0xFF})
DEFAULT_CHARGING_REMAINING_INVALID: frozenset[int] = frozenset({0x3FE, 0x3FF, 0x7FE, 0x7FF})


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
    vin: str = ""


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
    ac_rear_heater: bool = False
    ac_rear_vent: bool = False
    ac_steering_wheel_heater: bool = False
    ac_air_purification: bool = False
    ac_front_windshield_heater: bool = False
    roof_sunshade: bool = False
    rear_window_defog: bool = False


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


def parse_vehicle_control_config(raw: Any) -> VehicleControlConfig:
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
        ac_rear_heater=bool(ac.get("RearHeater")),
        ac_rear_vent=bool(ac.get("RearVent")),
        ac_steering_wheel_heater=bool(cfg.get("SteeringWheelHeater")),
        ac_air_purification=bool(ac.get("AirPurification")),
        ac_front_windshield_heater=bool(cfg.get("FrontWindshieldHeater")),
        roof_sunshade=bool(cfg.get("sunroofSunshade")),
        rear_window_defog=bool(ac.get("rearWindowDefog")),
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
