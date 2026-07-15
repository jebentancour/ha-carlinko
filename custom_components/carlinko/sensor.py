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
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import RAW_TEST_BYTES
from .const import CONF_VEHICLE_ID, CONF_VEHICLE_MODEL, CONF_VEHICLE_PLATE, CONF_VEHICLE_VIN, DOMAIN
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
        key="range_km",
        translation_key="range",
        icon="mdi:map-marker-distance",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("range_km"),
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
        key="battery_power_kw",
        translation_key="battery_power",
        icon="mdi:battery-charging-outline",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("battery_power_kw"),
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
            name=self._entry.data.get(CONF_VEHICLE_MODEL) or "CarLinko EV",
            manufacturer="CarLinko (Chery / Jaecoo / Omoda)",
            model=self._entry.data.get(CONF_VEHICLE_MODEL),
            serial_number=self._entry.data.get(CONF_VEHICLE_VIN) or None,
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


class CarLinkoRawByteSensor(_CarLinkoEntityBase, SensorEntity):
    """Raw, unscaled value of a byte whose meaning isn't confirmed yet — for testing."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:flask-outline"

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry, byte_n: int) -> None:
        super().__init__(coordinator, entry)
        self._byte_n = byte_n
        self._attr_name = f"Raw Byte {byte_n}"
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_raw_byte{byte_n}"

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(f"raw_byte{self._byte_n}")
