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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_VEHICLE_ID, CONF_VEHICLE_MODEL, CONF_VEHICLE_VIN, DOMAIN
from .coordinator import CarLinkoCoordinator


@dataclass(frozen=True, kw_only=True)
class CarLinkoBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any] = lambda data: None


# Confirmed 2026-07-14 by opening/closing each door and the trunk one at a time and
# watching which byte moved (byte 2 = 4-bit door mask, byte 4 = trunk) — see
# api.py's decode_blob() docstring.
BINARY_SENSORS: tuple[CarLinkoBinarySensorDescription, ...] = (
    CarLinkoBinarySensorDescription(
        key="door_driver",
        translation_key="door_driver",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: d.get("door_driver"),
    ),
    CarLinkoBinarySensorDescription(
        key="door_passenger",
        translation_key="door_passenger",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: d.get("door_passenger"),
    ),
    CarLinkoBinarySensorDescription(
        key="door_rear_driver",
        translation_key="door_rear_driver",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: d.get("door_rear_driver"),
    ),
    CarLinkoBinarySensorDescription(
        key="door_rear_passenger",
        translation_key="door_rear_passenger",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: d.get("door_rear_passenger"),
    ),
    CarLinkoBinarySensorDescription(
        key="trunk_open",
        translation_key="trunk_open",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=lambda d: d.get("trunk_open"),
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: CarLinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [CarLinkoOnlineSensor(coordinator, entry)]
    entities += [CarLinkoBinarySensor(coordinator, entry, desc) for desc in BINARY_SENSORS]
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
            name=self._entry.data.get(CONF_VEHICLE_MODEL) or "CarLinko EV",
            manufacturer="CarLinko (Chery / Jaecoo / Omoda)",
            model=self._entry.data.get(CONF_VEHICLE_MODEL),
            serial_number=self._entry.data.get(CONF_VEHICLE_VIN) or None,
        )


class CarLinkoOnlineSensor(_CarLinkoBinaryBase):
    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

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
