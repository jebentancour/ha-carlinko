"""Climate entity for the CarLinko integration.

Combines A/C power, target temperature and Quick Heat/Cool into a single entity.
Read-only for power and temperature — neither the plain A/C on/off opcode (`741001`/
`741000`) nor the set-temperature opcode (`7411` + payload, encoding still unconfirmed) has
been tested live, unlike Quick Heat/Cool (`741F01`/`741F00`, `742001`/`742000`), which have.
Only HEAT/COOL/AUTO are actually actuated (mapped onto Quick Heat/Cool on/off); selecting Off
reports what the car is doing but can't be commanded from here yet.
"""
from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
    _attr_supported_features = ClimateEntityFeature(0)

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

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        client = self.coordinator.client
        vehicle_id, device_sn = self._entry.data[CONF_VEHICLE_ID], self._entry.data[CONF_DEVICE_SN]
        if hvac_mode == HVACMode.HEAT:
            await client.quick_heat_on(vehicle_id, device_sn)
        elif hvac_mode == HVACMode.COOL:
            await client.quick_cool_on(vehicle_id, device_sn)
        elif hvac_mode == HVACMode.AUTO:
            # No dedicated "cancel quick mode" opcode — turning off both is harmless if one
            # was already off, and gets back to plain A/C without touching the temperature.
            await client.quick_heat_off(vehicle_id, device_sn)
            await client.quick_cool_off(vehicle_id, device_sn)
        else:
            raise HomeAssistantError(
                "Turning the A/C fully off isn't supported yet — the plain A/C on/off command "
                "hasn't been confirmed working. Turn it off from the car or the CarLinko app."
            )
        await self.coordinator.async_request_refresh()
