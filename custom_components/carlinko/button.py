"""Button entities for the CarLinko integration."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    entities: list[ButtonEntity] = []
    if data.get("control_charging"):
        entities.append(CarLinkoStopChargingButton(coordinator, entry))
    if data.get("control_find"):
        entities.append(CarLinkoFindCarButton(coordinator, entry))
    async_add_entities(entities)


class _CarLinkoButtonBase(CoordinatorEntity[CarLinkoCoordinator], ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.data[CONF_VEHICLE_ID])},
            name=self._entry.data[CONF_VEHICLE_PLATE],
            manufacturer=self._entry.data[CONF_VEHICLE_BRAND],
            model=self._entry.data[CONF_VEHICLE_MODEL],
            serial_number=self._entry.data[CONF_DEVICE_SN],
        )


class CarLinkoStopChargingButton(_CarLinkoButtonBase):
    _attr_translation_key = "stop_charging"
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "stop_charging")

    async def async_press(self) -> None:
        await self.coordinator.client.stop_charging(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        )
        await self.coordinator.async_request_refresh()


class CarLinkoFindCarButton(_CarLinkoButtonBase):
    _attr_translation_key = "find_car"
    _attr_icon = "mdi:map-marker"

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "find_car")

    async def async_press(self) -> None:
        await self.coordinator.client.find_car(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        )
