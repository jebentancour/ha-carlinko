"""Switch entity for the CarLinko integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CMD_DEFOG_FRONT_OFF,
    CMD_DEFOG_FRONT_ON,
    CMD_DEFOG_REAR_OFF,
    CMD_DEFOG_REAR_ON,
    CONF_DEVICE_SN,
    CONF_VEHICLE_BRAND,
    CONF_VEHICLE_ID,
    CONF_VEHICLE_MODEL,
    CONF_VEHICLE_PLATE,
    DOMAIN,
)
from .coordinator import CarLinkoCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: CarLinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    entities: list[SwitchEntity] = []
    if data.get("control_ac_defog"):
        entities.append(CarLinkoDefrostSwitch(coordinator, entry))
    if data.get("control_rear_window_defog"):
        entities.append(CarLinkoRearDefrostSwitch(coordinator, entry))
    async_add_entities(entities)


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
        await self.coordinator.client.send_control(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN], CMD_DEFOG_FRONT_ON
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.send_control(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN], CMD_DEFOG_FRONT_OFF
        )
        await self.coordinator.async_request_refresh()


class CarLinkoRearDefrostSwitch(CoordinatorEntity[CarLinkoCoordinator], SwitchEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "defrost_rear"
    _attr_icon = "mdi:car-defrost-rear"

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_defrost_rear"

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
        return self.coordinator.data.get("rear_window_defog")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.send_control(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN], CMD_DEFOG_REAR_ON
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.send_control(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN], CMD_DEFOG_REAR_OFF
        )
        await self.coordinator.async_request_refresh()
