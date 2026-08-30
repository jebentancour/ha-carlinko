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
        key="ac_on",
        translation_key="ac_on",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda d: d.get("ac_on"),
    ),
    CarLinkoBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: d.get("charging"),
    ),
)


CONTROL_CAPABILITY_SENSORS: tuple[CarLinkoBinarySensorDescription, ...] = (
    CarLinkoBinarySensorDescription(
        key="control_ac_switch",
        translation_key="control_ac_switch",
        icon="mdi:air-conditioner",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_switch"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_set_temperature",
        translation_key="control_ac_set_temperature",
        icon="mdi:thermostat",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_set_temperature"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_set_duration",
        translation_key="control_ac_set_duration",
        icon="mdi:timer-cog-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_set_duration"),
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: CarLinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [CarLinkoOnlineSensor(coordinator, entry)]
    entities += [CarLinkoBinarySensor(coordinator, entry, desc) for desc in BINARY_SENSORS]
    entities += [CarLinkoBinarySensor(coordinator, entry, desc) for desc in CONTROL_CAPABILITY_SENSORS]
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
