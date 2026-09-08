"""Climate entity for the CarLinko integration.

Combines A/C power, target temperature and Quick Heat/Cool into a single entity. Power
(`741001`/`741000`) and target temperature (`7411` + payload, see
`api.CarLinkoClient.set_ac_temperature()`) are both writable now, but neither opcode has been
fired live yet — unlike Quick Heat/Cool, which have. HEAT/COOL are actuated via the confirmed
Quick Heat/Cool opcodes; AUTO turns the A/C on and cancels whichever quick mode is active.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_SN, CONF_VEHICLE_BRAND, CONF_VEHICLE_ID, CONF_VEHICLE_MODEL, CONF_VEHICLE_PLATE, DOMAIN
from .coordinator import CarLinkoCoordinator

DEFAULT_MIN_TEMP = 16.0
DEFAULT_MAX_TEMP = 32.0


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: CarLinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    # Only offer the entity on cars whose vehicleControlConfig declares A/C support at all —
    # HEAT/COOL are gated per-mode below on the Rapid Heat/Cool flags specifically.
    if coordinator.data and coordinator.data.get("control_ac_switch"):
        async_add_entities([CarLinkoClimate(coordinator, entry)])


class CarLinkoClimate(CoordinatorEntity[CarLinkoCoordinator], ClimateEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "ac"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_ac"
        data = coordinator.data or {}
        modes = [HVACMode.OFF, HVACMode.AUTO]
        if data.get("control_ac_rapid_heat"):
            modes.append(HVACMode.HEAT)
        if data.get("control_ac_rapid_cool"):
            modes.append(HVACMode.COOL)
        self._attr_hvac_modes = modes
        features = ClimateEntityFeature(0)
        if data.get("control_ac_set_temperature"):
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
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
    def hvac_mode(self) -> HVACMode | None:
        data = self.coordinator.data
        if not data:
            return None
        ac_on = data.get("ac_on")
        if ac_on is None:
            return None
        if not ac_on:
            return HVACMode.OFF
        blower_gear = data.get("ac_blower_gear")
        if blower_gear == "high":
            return HVACMode.HEAT
        if blower_gear == "low":
            return HVACMode.COOL
        # Blower gear only updates on the frame Quick Heat/Cool actually kicks in; on every
        # other frame it carries no new info, so fall back to the temperature-extreme tell.
        ac_temp_c = data.get("ac_temp_c")
        if ac_temp_c is not None and ac_temp_c == data.get("ac_temp_max"):
            return HVACMode.HEAT
        if ac_temp_c is not None and ac_temp_c == data.get("ac_temp_min"):
            return HVACMode.COOL
        return HVACMode.AUTO

    @property
    def target_temperature(self) -> float | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("ac_temp_c")

    @property
    def min_temp(self) -> float:
        return (self.coordinator.data or {}).get("ac_temp_min") or DEFAULT_MIN_TEMP

    @property
    def max_temp(self) -> float:
        return (self.coordinator.data or {}).get("ac_temp_max") or DEFAULT_MAX_TEMP

    @property
    def target_temperature_step(self) -> float | None:
        return (self.coordinator.data or {}).get("ac_temp_step")

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.coordinator.client.set_ac_temperature(
            self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN], temperature
        )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        client = self.coordinator.client
        vehicle_id, device_sn = self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        if hvac_mode == HVACMode.HEAT:
            await client.quick_heat_on(vehicle_id, device_sn)
        elif hvac_mode == HVACMode.COOL:
            await client.quick_cool_on(vehicle_id, device_sn)
        elif hvac_mode == HVACMode.AUTO:
            # Explicit power-on covers the Off -> Auto transition (quick-mode-off alone
            # wouldn't turn the A/C on); harmless no-op if it was already on. No dedicated
            # "cancel quick mode" opcode either — turning off both is harmless if one was
            # already off, and gets back to plain A/C without touching the temperature.
            await client.ac_power_on(vehicle_id, device_sn)
            await client.quick_heat_off(vehicle_id, device_sn)
            await client.quick_cool_off(vehicle_id, device_sn)
        else:
            await client.ac_power_off(vehicle_id, device_sn)
        await self.coordinator.async_request_refresh()
