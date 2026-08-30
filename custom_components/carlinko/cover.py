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
    data = coordinator.data or {}
    entities: list[CoverEntity] = []
    # Only offer each cover on cars whose vehicleControlConfig declares the matching
    # capability — firing an opcode the car doesn't support would just error.
    if data.get("control_liftgate"):
        entities.append(CarLinkoLiftgateCover(coordinator, entry))
    if data.get("control_sunroof"):
        entities.append(CarLinkoSunroofCover(coordinator, entry))
    async_add_entities(entities)


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


class CarLinkoSunroofCover(CoordinatorEntity[CarLinkoCoordinator], CoverEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "sunroof"
    _attr_device_class = CoverDeviceClass.WINDOW

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_sunroof"
        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        # SunroofTilting is a separate capability flag from Sunroof itself — only advertise
        # the vent/tilt actions if this car's config actually declares it.
        if coordinator.data and coordinator.data.get("control_sunroof_tilt"):
            features |= CoverEntityFeature.OPEN_TILT | CoverEntityFeature.CLOSE_TILT
        self._attr_supported_features = features

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
        open_ = self.coordinator.data.get("sunroof_open")
        return None if open_ is None else not open_

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self.coordinator.client.open_sunroof(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        )
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self.coordinator.client.close_sunroof(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        )
        await self.coordinator.async_request_refresh()

    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        await self.coordinator.client.tilt_sunroof(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        )
        await self.coordinator.async_request_refresh()

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        # There's no separate "leave closed but untilt" opcode — the car only has
        # close/open/vent states, so closing the tilt is the same command as closing outright.
        await self.coordinator.client.close_sunroof(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        )
        await self.coordinator.async_request_refresh()
