"""Binary sensors for the CarLinko integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_SN, CONF_VEHICLE_BRAND, CONF_VEHICLE_ID, CONF_VEHICLE_MODEL, CONF_VEHICLE_PLATE, DOMAIN
from .coordinator import CarLinkoCoordinator


@dataclass(frozen=True, kw_only=True)
class CarLinkoBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any] = lambda data: None
    enabled_if: Callable[[dict[str, Any]], bool] | None = None


BINARY_SENSORS: tuple[CarLinkoBinarySensorDescription, ...] = (
    CarLinkoBinarySensorDescription(
        key="door_front_left",
        translation_key="door_front_left",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: d.get("door_front_left"),
    ),
    CarLinkoBinarySensorDescription(
        key="door_front_right",
        translation_key="door_front_right",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: d.get("door_front_right"),
    ),
    CarLinkoBinarySensorDescription(
        key="door_rear_left",
        translation_key="door_rear_left",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: d.get("door_rear_left"),
    ),
    CarLinkoBinarySensorDescription(
        key="door_rear_right",
        translation_key="door_rear_right",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: d.get("door_rear_right"),
    ),
    CarLinkoBinarySensorDescription(
        key="ignition",
        translation_key="ignition",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda d: d.get("ignition_on"),
    ),
    CarLinkoBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: d.get("charging"),
    ),
    CarLinkoBinarySensorDescription(
        key="ac_compressor",
        translation_key="ac_compressor",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:air-conditioner",
        value_fn=lambda d: d.get("ac_compressor"),
    ),
    # Climate extras, only on cars that report the matching capability.
    CarLinkoBinarySensorDescription(
        key="steering_wheel_heat",
        translation_key="steering_wheel_heat",
        icon="mdi:steering",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("steering_wheel_heat"),
        enabled_if=lambda d: bool(d.get("control_ac_steering_wheel_heater")),
    ),
    CarLinkoBinarySensorDescription(
        key="air_purifier",
        translation_key="air_purifier",
        icon="mdi:air-purifier",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("air_purifier"),
        enabled_if=lambda d: bool(d.get("control_ac_air_purification")),
    ),
    CarLinkoBinarySensorDescription(
        key="windshield_heat",
        translation_key="windshield_heat",
        icon="mdi:car-defrost-front",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("windshield_heat"),
        enabled_if=lambda d: bool(d.get("control_ac_front_windshield_heater")),
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: CarLinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    entities: list[BinarySensorEntity] = [CarLinkoOnlineSensor(coordinator, entry)]
    entities += [
        CarLinkoBinarySensor(coordinator, entry, desc)
        for desc in BINARY_SENSORS
        if desc.enabled_if is None or desc.enabled_if(data)
    ]
    async_add_entities(entities)


class _CarLinkoBinaryBase(CoordinatorEntity[CarLinkoCoordinator], BinarySensorEntity):
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


class CarLinkoOnlineSensor(_CarLinkoBinaryBase):
    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_online"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return bool(self.coordinator.data.get("online"))


class CarLinkoBinarySensor(_CarLinkoBinaryBase):
    entity_description: CarLinkoBinarySensorDescription

    def __init__(
        self, coordinator: CarLinkoCoordinator, entry: ConfigEntry, description: CarLinkoBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
