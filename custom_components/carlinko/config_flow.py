"""Config flow: email + password + region -> login -> auto-detect vehicle."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CarLinkoAuthError, CarLinkoClient, CarLinkoConnectionError, VehicleInfo
from .const import (
    CONF_DEVICE_SN,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_VEHICLE_ID,
    CONF_VEHICLE_MODEL,
    CONF_VEHICLE_PLATE,
    CONF_VEHICLE_VIN,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_REGION, default=DEFAULT_REGION): str,
    }
)


class CarLinkoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a CarLinko config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._password: str | None = None
        self._region: str = DEFAULT_REGION
        self._vehicles: list[VehicleInfo] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]
            self._region = user_input[CONF_REGION] or DEFAULT_REGION

            session = async_get_clientsession(self.hass)
            client = CarLinkoClient(session, self._email, self._password, self._region)
            try:
                await client.login()
                self._vehicles = await client.get_vehicles()
            except CarLinkoAuthError:
                errors["base"] = "invalid_auth"
            except CarLinkoConnectionError:
                errors["base"] = "cannot_connect"
            else:
                if not self._vehicles:
                    errors["base"] = "no_vehicles"
                elif len(self._vehicles) == 1:
                    return await self._finish(self._vehicles[0])
                else:
                    return await self.async_step_pick_vehicle()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    async def async_step_pick_vehicle(self, user_input: dict[str, Any] | None = None) -> Any:
        if user_input is not None:
            chosen = next(v for v in self._vehicles if v.vehicle_id == user_input[CONF_VEHICLE_ID])
            return await self._finish(chosen)

        options = {v.vehicle_id: f"{v.model} ({v.plate or v.vin or v.vehicle_id})" for v in self._vehicles}
        schema = vol.Schema({vol.Required(CONF_VEHICLE_ID): vol.In(options)})
        return self.async_show_form(step_id="pick_vehicle", data_schema=schema)

    async def _finish(self, vehicle: VehicleInfo) -> Any:
        await self.async_set_unique_id(vehicle.vehicle_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=vehicle.model or "CarLinko EV",
            data={
                CONF_EMAIL: self._email,
                CONF_PASSWORD: self._password,
                CONF_REGION: self._region,
                CONF_VEHICLE_ID: vehicle.vehicle_id,
                CONF_DEVICE_SN: vehicle.device_sn,
                CONF_VEHICLE_MODEL: vehicle.model,
                CONF_VEHICLE_VIN: vehicle.vin,
                CONF_VEHICLE_PLATE: vehicle.plate,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CarLinkoOptionsFlow(config_entry)


class CarLinkoOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self._entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
