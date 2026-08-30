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


# (entity-id position suffix, telemetry dict key) for each of the 4 window covers.
_WINDOWS: tuple[tuple[str, str], ...] = (
    ("front_left", "window_front_left"),
    ("front_right", "window_front_right"),
    ("rear_left", "window_rear_left"),
    ("rear_right", "window_rear_right"),
)


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
    if data.get("control_windows_open") or data.get("control_windows_close"):
        entities += [CarLinkoWindowCover(coordinator, entry, position, key) for position, key in _WINDOWS]
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
        state = self.coordinator.data.get("sunroof_state")
        return None if state is None else state == "closed"

    @property
    def current_cover_tilt_position(self) -> int | None:
        # No graduated position, just closed/open/tilted — represent the vent state as fully
        # tilted (100) vs. not (0), same closed/open-only convention as is_closed above.
        if not self.coordinator.data:
            return None
        state = self.coordinator.data.get("sunroof_state")
        return None if state is None else (100 if state == "tilted" else 0)

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


class CarLinkoWindowCover(CoordinatorEntity[CarLinkoCoordinator], CoverEntity):
    """One of the 4 window covers. CarLinko only has a single all-windows opcode, not a
    per-window one, so opening/closing/venting any one of these moves every window on the car.
    """

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.WINDOW

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry, position: str, data_key: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._data_key = data_key
        self._attr_translation_key = f"window_{position}"
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_window_{position}"
        data = coordinator.data or {}
        features = CoverEntityFeature(0)
        if data.get("control_windows_open"):
            features |= CoverEntityFeature.OPEN
        if data.get("control_windows_close"):
            features |= CoverEntityFeature.CLOSE
        if data.get("control_windows_vent"):
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
        state = self.coordinator.data.get(self._data_key)
        return None if state is None else state == "closed"

    @property
    def current_cover_tilt_position(self) -> int | None:
        # Same closed/open-only convention as the sunroof: no graduated position, just the
        # three states, so "vent" reads as fully tilted (100).
        if not self.coordinator.data:
            return None
        state = self.coordinator.data.get(self._data_key)
        return None if state is None else (100 if state == "vent" else 0)

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self.coordinator.client.open_windows(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        )
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self.coordinator.client.close_windows(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        )
        await self.coordinator.async_request_refresh()

    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        await self.coordinator.client.vent_windows(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        )
        await self.coordinator.async_request_refresh()

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        # No distinct "leave closed but unvent" opcode, same as the sunroof above.
        await self.coordinator.client.close_windows(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        )
        await self.coordinator.async_request_refresh()
