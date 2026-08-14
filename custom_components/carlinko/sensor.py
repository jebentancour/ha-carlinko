"""Sensor entities for the CarLinko integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CHARGING_CONNECTOR_STATES, CHARGING_STATUSES, RAW_TEST_BYTES, RAW_WORD_PAIRS, SEAT_LEVELS
from .const import CONF_DEVICE_SN, CONF_VEHICLE_BRAND, CONF_VEHICLE_ID, CONF_VEHICLE_MODEL, CONF_VEHICLE_PLATE, DOMAIN
from .coordinator import CarLinkoCoordinator

TYRE_LABELS = ("Front Left", "Front Right", "Rear Left", "Rear Right")


@dataclass(frozen=True, kw_only=True)
class CarLinkoSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any] = lambda data: None


SENSORS: tuple[CarLinkoSensorDescription, ...] = (
    CarLinkoSensorDescription(
        key="battery_pct",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("battery_pct"),
    ),
    CarLinkoSensorDescription(
        key="battery_range_km",
        translation_key="battery_range",
        icon="mdi:map-marker-distance",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("battery_range_km"),
    ),
    CarLinkoSensorDescription(
        key="odometer_km",
        translation_key="odometer",
        icon="mdi:counter",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.get("odometer_km"),
    ),
    CarLinkoSensorDescription(
        key="volt12",
        translation_key="volt12",
        icon="mdi:car-battery",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("volt12"),
    ),
    CarLinkoSensorDescription(
        key="speed_kmh",
        translation_key="speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("speed_kmh"),
    ),
    CarLinkoSensorDescription(
        key="consumption_kwh_100km",
        translation_key="consumption",
        icon="mdi:lightning-bolt",
        native_unit_of_measurement="kWh/100km",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("consumption_kwh_100km"),
    ),
    CarLinkoSensorDescription(
        key="power_kw",
        translation_key="power",
        icon="mdi:flash",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("power_kw"),
    ),
    CarLinkoSensorDescription(
        key="regen_power_kw",
        translation_key="regen_power",
        icon="mdi:battery-charging",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("regen_power_kw"),
    ),
    CarLinkoSensorDescription(
        key="charge_power_kw",
        translation_key="charge_power",
        icon="mdi:ev-station",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("charge_power_kw"),
    ),
    CarLinkoSensorDescription(
        key="charging_status",
        translation_key="charging_status",
        icon="mdi:ev-station",
        device_class=SensorDeviceClass.ENUM,
        options=list(CHARGING_STATUSES.values()),
        value_fn=lambda d: d.get("charging_status"),
    ),
    CarLinkoSensorDescription(
        key="charging_connector",
        translation_key="charging_connector",
        icon="mdi:ev-plug-type2",
        device_class=SensorDeviceClass.ENUM,
        options=list(CHARGING_CONNECTOR_STATES.values()),
        value_fn=lambda d: d.get("charging_connector"),
    ),
    CarLinkoSensorDescription(
        key="charging_remaining_min",
        translation_key="charging_remaining",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("charging_remaining_min"),
    ),
    CarLinkoSensorDescription(
        key="wltp_range_km",
        translation_key="wltp_range",
        icon="mdi:map-marker-distance",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("wltp_range_km"),
    ),
    CarLinkoSensorDescription(
        key="range_km",
        translation_key="range",
        icon="mdi:map-marker-distance",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("range_km"),
    ),
    CarLinkoSensorDescription(
        key="fuel_pct",
        translation_key="fuel_level",
        icon="mdi:gas-station",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("fuel_pct"),
    ),
    CarLinkoSensorDescription(
        key="fuel_l_100",
        translation_key="fuel_consumption",
        icon="mdi:gas-station",
        native_unit_of_measurement="L/100km",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("fuel_l_100"),
    ),
    CarLinkoSensorDescription(
        key="powertrain",
        translation_key="powertrain",
        icon="mdi:car-electric-outline",
        device_class=SensorDeviceClass.ENUM,
        options=["bev", "phev"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("powertrain"),
    ),
    CarLinkoSensorDescription(
        key="ac_temp_c",
        translation_key="ac_temp",
        icon="mdi:thermostat",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("ac_temp_c"),
    ),
    CarLinkoSensorDescription(
        key="seat_heat_left",
        translation_key="seat_heat_left",
        icon="mdi:car-seat-heater",
        device_class=SensorDeviceClass.ENUM,
        options=list(SEAT_LEVELS.values()),
        value_fn=lambda d: d.get("seat_heat_left"),
    ),
    CarLinkoSensorDescription(
        key="seat_heat_right",
        translation_key="seat_heat_right",
        icon="mdi:car-seat-heater",
        device_class=SensorDeviceClass.ENUM,
        options=list(SEAT_LEVELS.values()),
        value_fn=lambda d: d.get("seat_heat_right"),
    ),
    CarLinkoSensorDescription(
        key="seat_vent_left",
        translation_key="seat_vent_left",
        icon="mdi:car-seat-cooler",
        device_class=SensorDeviceClass.ENUM,
        options=list(SEAT_LEVELS.values()),
        value_fn=lambda d: d.get("seat_vent_left"),
    ),
    CarLinkoSensorDescription(
        key="seat_vent_right",
        translation_key="seat_vent_right",
        icon="mdi:car-seat-cooler",
        device_class=SensorDeviceClass.ENUM,
        options=list(SEAT_LEVELS.values()),
        value_fn=lambda d: d.get("seat_vent_right"),
    ),
    # From `/user/device/manage/terminalNoticeConfig/{id}` (api.decode_notice_config) — trip and
    # charge schedules, both diagnostic. Booleans for these live in binary_sensor.py instead.
    CarLinkoSensorDescription(
        key="trip_schedule_time",
        translation_key="trip_schedule_time",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("trip_schedule_time"),
    ),
    CarLinkoSensorDescription(
        key="trip_schedule_days",
        translation_key="trip_schedule_days",
        icon="mdi:calendar-week",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("trip_schedule_days"),
    ),
    CarLinkoSensorDescription(
        key="charge_target_soc",
        translation_key="charge_target_soc",
        icon="mdi:battery-charging-high",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("charge_target_soc"),
    ),
    CarLinkoSensorDescription(
        key="charge_schedule_time",
        translation_key="charge_schedule_time",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("charge_schedule_time"),
    ),
    CarLinkoSensorDescription(
        key="charge_schedule_duration_h",
        translation_key="charge_schedule_duration",
        icon="mdi:timer-outline",
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("charge_schedule_duration_h"),
    ),
    CarLinkoSensorDescription(
        key="charge_schedule_days",
        translation_key="charge_schedule_days",
        icon="mdi:calendar-week",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("charge_schedule_days"),
    ),
    # From `vehicleControlConfig` (api._parse_vehicle_control_config) — per-model constants that
    # aren't simple capability booleans (those are control_* in binary_sensor.py instead).
    CarLinkoSensorDescription(
        key="trunk_type",
        translation_key="trunk_type",
        icon="mdi:car-back",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("trunk_type"),
    ),
    CarLinkoSensorDescription(
        key="charging_cycle",
        translation_key="charging_cycle",
        icon="mdi:refresh",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("charging_cycle"),
    ),
    CarLinkoSensorDescription(
        key="ac_temp_min",
        translation_key="ac_temp_min",
        icon="mdi:thermometer-low",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("ac_temp_min"),
    ),
    CarLinkoSensorDescription(
        key="ac_temp_max",
        translation_key="ac_temp_max",
        icon="mdi:thermometer-high",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("ac_temp_max"),
    ),
    CarLinkoSensorDescription(
        key="ac_temp_step",
        translation_key="ac_temp_step",
        icon="mdi:thermometer-lines",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("ac_temp_step"),
    ),
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: CarLinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [CarLinkoSensor(coordinator, entry, desc) for desc in SENSORS]
    for wheel_idx, label in enumerate(TYRE_LABELS):
        entities.append(CarLinkoTyreSensor(coordinator, entry, wheel_idx, label, "tyre_psi", UnitOfPressure.PSI, SensorDeviceClass.PRESSURE))
        entities.append(
            CarLinkoTyreSensor(
                coordinator, entry, wheel_idx, label, "tyre_temp_c", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE
            )
        )
    entities += [CarLinkoRawByteSensor(coordinator, entry, n) for n in RAW_TEST_BYTES]
    entities += [CarLinkoRawWordSensor(coordinator, entry, hi, lo) for hi, lo in RAW_WORD_PAIRS]
    async_add_entities(entities)


class _CarLinkoEntityBase(CoordinatorEntity[CarLinkoCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.data[CONF_VEHICLE_ID])},
            name=self._entry.data[CONF_VEHICLE_PLATE],
            manufacturer=self._entry.data[CONF_VEHICLE_BRAND],
            model=self._entry.data[CONF_VEHICLE_MODEL],
            serial_number=self._entry.data[CONF_DEVICE_SN],
        )


class CarLinkoSensor(_CarLinkoEntityBase, SensorEntity):
    entity_description: CarLinkoSensorDescription

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry, description: CarLinkoSensorDescription) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_{description.key}"

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class CarLinkoTyreSensor(_CarLinkoEntityBase, SensorEntity):
    def __init__(
        self,
        coordinator: CarLinkoCoordinator,
        entry: ConfigEntry,
        wheel_idx: int,
        label: str,
        data_key: str,
        unit: str,
        device_class: SensorDeviceClass,
    ) -> None:
        super().__init__(coordinator, entry)
        self._wheel_idx = wheel_idx
        self._data_key = data_key
        kind = "Pressure" if data_key == "tyre_psi" else "Temperature"
        self._attr_name = f"Tyre {label} {kind}"
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_{data_key}_{wheel_idx}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:car-tire-alert"

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        values = self.coordinator.data.get(self._data_key)
        if not values or self._wheel_idx >= len(values):
            return None
        return values[self._wheel_idx]


RAW_BYTE_LABELS: dict[int, str] = {}
RAW_BYTE_UNITS: dict[int, tuple[str, float]] = {}
RAW_WORD_LABELS: dict[tuple[int, int], str] = {}


class CarLinkoRawByteSensor(_CarLinkoEntityBase, SensorEntity):
    """Raw value of a byte whose meaning isn't confirmed yet — for testing."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:flask-outline"

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry, byte_n: int) -> None:
        super().__init__(coordinator, entry)
        self._byte_n = byte_n
        label = RAW_BYTE_LABELS.get(byte_n, f"Raw Byte {byte_n}")
        self._attr_name = f"{label} (byte {byte_n})"
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_raw_byte{byte_n}"
        self._scale: float | None = None
        if byte_n in RAW_BYTE_UNITS:
            unit, self._scale = RAW_BYTE_UNITS[byte_n]
            self._attr_native_unit_of_measurement = unit
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        raw = self.coordinator.data.get(f"raw_byte{self._byte_n}")
        if raw is None or self._scale is None:
            return raw
        return round(raw * self._scale, 1)


class CarLinkoRawWordSensor(_CarLinkoEntityBase, SensorEntity):
    """Raw value of a high/low byte pair combined into a 16-bit value — for testing."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:flask-outline"

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry, hi: int, lo: int) -> None:
        super().__init__(coordinator, entry)
        self._key = f"raw_word{hi}_{lo}"
        label = RAW_WORD_LABELS.get((hi, lo), f"Raw Word {hi}:{lo}")
        self._attr_name = f"{label} (bytes {hi}:{lo})"
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_{self._key}"

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._key)
