"""Switch entity for the CarLinko integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_SN, CONF_VEHICLE_BRAND, CONF_VEHICLE_ID, CONF_VEHICLE_MODEL, CONF_VEHICLE_PLATE, DOMAIN
from .coordinator import CarLinkoCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: CarLinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.data and coordinator.data.get("control_ac_defog"):
        async_add_entities([CarLinkoDefrostSwitch(coordinator, entry)])


class CarLinkoDefrostSwitch(CoordinatorEntity[CarLinkoCoordinator], SwitchEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "defrost_front"
    _attr_icon = "mdi:car-defrost-front"

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_defrost_front"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.data[CONF_VEHICLE_ID])},
            name=self._entry.data[CONF_VEHICLE_PLATE],
            manufacturer=self._entry.data[CONF_VEHICLE_BRAND],
            model=self._entry.data[CONF_VEHICLE_MODEL],
            serial_number=self._entry.data[CONF_DEVICE_SN],
        )

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("defrost_front")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.defrost_on(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.defrost_off(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        )
        await self.coordinator.async_request_refresh()
