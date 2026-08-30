"""Switch entities for the CarLinko integration."""
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
    data = coordinator.data or {}
    entities: list[SwitchEntity] = []
    # Only offer each switch on cars whose vehicleControlConfig declares the matching
    # capability — firing an opcode the car doesn't support would just error.
    if data.get("control_ac_defog"):
        entities.append(CarLinkoDefrostSwitch(coordinator, entry))
    if data.get("control_ac_rapid_heat"):
        entities.append(CarLinkoQuickHeatSwitch(coordinator, entry))
    if data.get("control_ac_rapid_cool"):
        entities.append(CarLinkoQuickCoolSwitch(coordinator, entry))
    async_add_entities(entities)


class _CarLinkoSwitchBase(CoordinatorEntity[CarLinkoCoordinator], SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_translation_key = key
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

    def _vehicle_device(self) -> tuple[str, str]:
        return self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]


class CarLinkoDefrostSwitch(_CarLinkoSwitchBase):
    _attr_icon = "mdi:car-defrost-front"

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "defrost_front")

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("defrost_front")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.defrost_on(*self._vehicle_device())
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.defrost_off(*self._vehicle_device())
        await self.coordinator.async_request_refresh()


class _QuickAcSwitch(_CarLinkoSwitchBase):
    """Quick Heat/Cool have no dedicated telemetry bit yet (byte 67's meaning is unconfirmed —
    see the `raw_byte67` diagnostic sensor). Until that's nailed down, infer on/off from the
    known-confirmed climate fields: A/C on and its target temperature pinned to the model's
    extreme (max for quick heat, min for quick cool) — that's the behavior these modes drive.
    """

    _extreme_key: str  # "ac_temp_max" or "ac_temp_min", set by subclasses

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if not data:
            return None
        ac_on, ac_temp_c, extreme = data.get("ac_on"), data.get("ac_temp_c"), data.get(self._extreme_key)
        if ac_on is None or ac_temp_c is None or extreme is None:
            return None
        return bool(ac_on) and ac_temp_c == extreme


class CarLinkoQuickHeatSwitch(_QuickAcSwitch):
    _attr_icon = "mdi:fire"
    _extreme_key = "ac_temp_max"

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "quick_heat")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.quick_heat_on(*self._vehicle_device())
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.quick_heat_off(*self._vehicle_device())
        await self.coordinator.async_request_refresh()


class CarLinkoQuickCoolSwitch(_QuickAcSwitch):
    _attr_icon = "mdi:snowflake"
    _extreme_key = "ac_temp_min"

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "quick_cool")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.quick_cool_on(*self._vehicle_device())
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.quick_cool_off(*self._vehicle_device())
        await self.coordinator.async_request_refresh()
