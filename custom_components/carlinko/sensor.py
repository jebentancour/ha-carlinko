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

from .api import CHARGING_CONNECTOR_STATES, CHARGING_STATUSES
from .const import CONF_DEVICE_SN, CONF_VEHICLE_BRAND, CONF_VEHICLE_ID, CONF_VEHICLE_MODEL, CONF_VEHICLE_PLATE, DOMAIN
from .coordinator import CarLinkoCoordinator

TYRE_LABELS = ("Front Left", "Front Right", "Rear Left", "Rear Right")


@dataclass(frozen=True, kw_only=True)
class CarLinkoSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any] = lambda data: None
    extra_state_attributes_fn: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None
    enabled_if: Callable[[dict[str, Any]], bool] | None = None


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
        enabled_if=lambda d: bool(d.get("has_power_consumption")),
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
        translation_key="fuel_range",
        icon="mdi:gas-station",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("range_km"),
        enabled_if=lambda d: bool(d.get("has_engine")),
    ),
    CarLinkoSensorDescription(
        key="fuel_pct",
        translation_key="fuel_level",
        icon="mdi:gas-station",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("fuel_pct"),
        enabled_if=lambda d: bool(d.get("has_engine")),
    ),
    CarLinkoSensorDescription(
        key="fuel_l_100",
        translation_key="fuel_consumption",
        icon="mdi:gas-station",
        native_unit_of_measurement="L/100km",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("fuel_l_100"),
        enabled_if=lambda d: bool(d.get("has_fuel_consumption")),
    ),
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: CarLinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    entities: list[SensorEntity] = [
        CarLinkoSensor(coordinator, entry, desc) for desc in SENSORS if desc.enabled_if is None or desc.enabled_if(data)
    ]
    for wheel_idx, label in enumerate(TYRE_LABELS):
        entities.append(CarLinkoTyreSensor(coordinator, entry, wheel_idx, label, "tyre_psi", UnitOfPressure.PSI, SensorDeviceClass.PRESSURE))
        entities.append(
            CarLinkoTyreSensor(
                coordinator, entry, wheel_idx, label, "tyre_temp_c", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE
            )
        )
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

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.coordinator.data or self.entity_description.extra_state_attributes_fn is None:
            return None
        return self.entity_description.extra_state_attributes_fn(self.coordinator.data)


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


