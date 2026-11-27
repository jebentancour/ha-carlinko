"""Switch entities for the CarLinko integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CMD_AIR_PURIFIER_OFF,
    CMD_AIR_PURIFIER_ON,
    CMD_DEFOG_FRONT_OFF,
    CMD_DEFOG_FRONT_ON,
    CMD_DEFOG_REAR_OFF,
    CMD_DEFOG_REAR_ON,
    CMD_STEERING_WHEEL_HEAT_OFF,
    CMD_STEERING_WHEEL_HEAT_ON,
    CMD_WINDSHIELD_HEAT_OFF,
    CMD_WINDSHIELD_HEAT_ON,
    CONF_DEVICE_SN,
    CONF_VEHICLE_BRAND,
    CONF_VEHICLE_ID,
    CONF_VEHICLE_MODEL,
    CONF_VEHICLE_PLATE,
    DOMAIN,
)
from .coordinator import CarLinkoCoordinator


@dataclass(frozen=True, kw_only=True)
class CarLinkoSwitchDescription(SwitchEntityDescription):
    capability: str
    state_key: str
    cmd_on: str
    cmd_off: str


SWITCHES: tuple[CarLinkoSwitchDescription, ...] = (
    CarLinkoSwitchDescription(
        key="defrost_front",
        translation_key="defrost_front",
        icon="mdi:car-defrost-front",
        capability="control_ac_defog",
        state_key="defrost_front",
        cmd_on=CMD_DEFOG_FRONT_ON,
        cmd_off=CMD_DEFOG_FRONT_OFF,
    ),
    CarLinkoSwitchDescription(
        key="defrost_rear",
        translation_key="defrost_rear",
        icon="mdi:car-defrost-rear",
        capability="control_rear_window_defog",
        state_key="rear_window_defog",
        cmd_on=CMD_DEFOG_REAR_ON,
        cmd_off=CMD_DEFOG_REAR_OFF,
    ),
    CarLinkoSwitchDescription(
        key="windshield_heat",
        translation_key="windshield_heat",
        icon="mdi:car-windshield",
        capability="control_ac_front_windshield_heater",
        state_key="windshield_heat",
        cmd_on=CMD_WINDSHIELD_HEAT_ON,
        cmd_off=CMD_WINDSHIELD_HEAT_OFF,
    ),
    CarLinkoSwitchDescription(
        key="steering_wheel_heat",
        translation_key="steering_wheel_heat",
        icon="mdi:steering",
        capability="control_ac_steering_wheel_heater",
        state_key="steering_wheel_heat",
        cmd_on=CMD_STEERING_WHEEL_HEAT_ON,
        cmd_off=CMD_STEERING_WHEEL_HEAT_OFF,
    ),
    CarLinkoSwitchDescription(
        key="air_purifier",
        translation_key="air_purifier",
        icon="mdi:air-purifier",
        capability="control_ac_air_purification",
        state_key="air_purifier",
        cmd_on=CMD_AIR_PURIFIER_ON,
        cmd_off=CMD_AIR_PURIFIER_OFF,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: CarLinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    async_add_entities(
        CarLinkoSwitch(coordinator, entry, desc) for desc in SWITCHES if data.get(desc.capability)
    )


class CarLinkoSwitch(CoordinatorEntity[CarLinkoCoordinator], SwitchEntity):
    _attr_has_entity_name = True
    entity_description: CarLinkoSwitchDescription

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry, description: CarLinkoSwitchDescription) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_{description.key}"

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
        return self.coordinator.data.get(self.entity_description.state_key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.send_control(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN], self.entity_description.cmd_on
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.send_control(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN], self.entity_description.cmd_off
        )
        await self.coordinator.async_request_refresh()
