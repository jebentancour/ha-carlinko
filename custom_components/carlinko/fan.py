"""Fan entities (seat heat/vent) for the CarLinko integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import ordered_list_item_to_percentage, percentage_to_ordered_list_item

from .const import CONF_DEVICE_SN, CONF_VEHICLE_BRAND, CONF_VEHICLE_ID, CONF_VEHICLE_MODEL, CONF_VEHICLE_PLATE, DOMAIN
from .coordinator import CarLinkoCoordinator

# SEAT_LEVELS in api.py is {0: "off", 1: "low", 2: "medium", 3: "high"} — speed steps exclude "off".
SPEEDS: tuple[str, ...] = ("low", "medium", "high")

# (unique-id/data-key suffix, icon, capability flag, CarLinkoClient setter method name).
# Heat and vent are independent bytes/opcodes per seat, so each gets its own fan entity rather
# than folding both into one entity with a heat/cool preset mode.
_SEAT_FANS: tuple[tuple[str, str, str, str], ...] = (
    ("seat_heat_left", "mdi:car-seat-heater", "control_ac_driver_heater", "set_seat_heat_left"),
    ("seat_heat_right", "mdi:car-seat-heater", "control_ac_assistant_heater", "set_seat_heat_right"),
    ("seat_vent_left", "mdi:car-seat-cooler", "control_ac_driver_vent", "set_seat_vent_left"),
    ("seat_vent_right", "mdi:car-seat-cooler", "control_ac_assistant_vent", "set_seat_vent_right"),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: CarLinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    # Only offer each fan on cars whose vehicleControlConfig declares the matching capability
    # — firing an opcode the car doesn't support would just error.
    entities = [
        CarLinkoSeatFan(coordinator, entry, key, icon, setter)
        for key, icon, capability, setter in _SEAT_FANS
        if data.get(capability)
    ]
    async_add_entities(entities)


class CarLinkoSeatFan(CoordinatorEntity[CarLinkoCoordinator], FanEntity):
    _attr_has_entity_name = True
    _attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    _attr_speed_count = len(SPEEDS)

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry, key: str, icon: str, setter: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._data_key = key
        self._setter = setter
        self._attr_translation_key = key
        self._attr_icon = icon
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

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        level = self.coordinator.data.get(self._data_key)
        return None if level is None else level != "off"

    @property
    def percentage(self) -> int | None:
        if not self.coordinator.data:
            return None
        level = self.coordinator.data.get(self._data_key)
        if level is None:
            return None
        return 0 if level == "off" else ordered_list_item_to_percentage(SPEEDS, level)

    async def _async_set_level(self, level: str) -> None:
        setter = getattr(self.coordinator.client, self._setter)
        await setter(self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN], level)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any
    ) -> None:
        level = percentage_to_ordered_list_item(SPEEDS, percentage) if percentage else SPEEDS[0]
        await self._async_set_level(level)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set_level("off")

    async def async_set_percentage(self, percentage: int) -> None:
        level = "off" if percentage == 0 else percentage_to_ordered_list_item(SPEEDS, percentage)
        await self._async_set_level(level)
