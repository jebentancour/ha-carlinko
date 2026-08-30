"""Cover entity for the CarLinko integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_SN, CONF_VEHICLE_BRAND, CONF_VEHICLE_ID, CONF_VEHICLE_MODEL, CONF_VEHICLE_PLATE, DOMAIN
from .coordinator import CarLinkoCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: CarLinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    # Only offer the liftgate on cars whose vehicleControlConfig declares PowerLiftgate
    # support — firing the opcode on a car that doesn't would just error.
    if coordinator.data and coordinator.data.get("control_liftgate"):
        async_add_entities([CarLinkoLiftgateCover(coordinator, entry)])


class CarLinkoLiftgateCover(CoordinatorEntity[CarLinkoCoordinator], CoverEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "liftgate"
    _attr_device_class = CoverDeviceClass.DOOR
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_liftgate"

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
    def is_closed(self) -> bool | None:
        if not self.coordinator.data:
            return None
        open_ = self.coordinator.data.get("liftgate_open")
        return None if open_ is None else not open_

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self.coordinator.client.open_liftgate(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        )
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self.coordinator.client.close_liftgate(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        )
        await self.coordinator.async_request_refresh()
