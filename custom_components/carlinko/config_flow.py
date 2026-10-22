"""Config flow: email + password + region -> login -> auto-detect vehicle."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode

from .api import CarLinkoAccountNotFoundError, CarLinkoAuthError, CarLinkoClient, CarLinkoConnectionError, VehicleInfo
from .const import (
    CONF_DEVICE_SN,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_VEHICLE_BRAND,
    CONF_VEHICLE_ID,
    CONF_VEHICLE_IMG_FRONT,
    CONF_VEHICLE_IMG_SIDE,
    CONF_VEHICLE_IMG_TOP,
    CONF_VEHICLE_MODEL,
    CONF_VEHICLE_PLATE,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    REGIONS,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_REGION, default=DEFAULT_REGION): SelectSelector(
            SelectSelectorConfig(options=list(REGIONS), mode=SelectSelectorMode.DROPDOWN, translation_key="region")
        ),
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
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]
            self._region = user_input[CONF_REGION] or DEFAULT_REGION

            session = async_get_clientsession(self.hass)
            client = CarLinkoClient(session, self._email, self._password, self._region, self.hass.config.time_zone)
            try:
                await client.login()
                self._vehicles = await client.get_vehicles()
            except CarLinkoAccountNotFoundError:
                errors["base"] = "account_not_found"
            except CarLinkoAuthError:
                errors["base"] = "invalid_auth"
            except CarLinkoConnectionError as err:
                _LOGGER.warning("Could not reach CarLinko region %s: %s", self._region, err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error talking to CarLinko region %s", self._region)
                errors["base"] = "unknown"
            else:
                if not self._vehicles:
                    errors["base"] = "no_vehicles"
                elif len(self._vehicles) == 1:
                    return await self._finish(self._vehicles[0])
                else:
                    return await self.async_step_pick_vehicle()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> Any:
        """Login was rejected with the stored password: ask for a new one."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> Any:
        entry = self._reauth_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = CarLinkoClient(
                session,
                entry.data[CONF_EMAIL],
                user_input[CONF_PASSWORD],
                entry.data[CONF_REGION],
                self.hass.config.time_zone,
            )
            try:
                await client.login()
            except CarLinkoAuthError:
                errors["base"] = "invalid_auth"
            except CarLinkoConnectionError as err:
                _LOGGER.warning("Could not reach CarLinko region %s: %s", entry.data[CONF_REGION], err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error talking to CarLinko region %s", entry.data[CONF_REGION])
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry, data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )

    async def async_step_pick_vehicle(self, user_input: dict[str, Any] | None = None) -> Any:
        if user_input is not None:
            chosen = next(v for v in self._vehicles if v.vehicle_id == user_input[CONF_VEHICLE_ID])
            return await self._finish(chosen)

        options = {v.vehicle_id: f"{v.model} ({v.plate})" for v in self._vehicles}
        schema = vol.Schema({vol.Required(CONF_VEHICLE_ID): vol.In(options)})
        return self.async_show_form(step_id="pick_vehicle", data_schema=schema)

    async def _finish(self, vehicle: VehicleInfo) -> Any:
        await self.async_set_unique_id(vehicle.vehicle_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="CarLinko",
            data={
                CONF_EMAIL: self._email,
                CONF_PASSWORD: self._password,
                CONF_REGION: self._region,
                CONF_VEHICLE_ID: vehicle.vehicle_id,
                CONF_DEVICE_SN: vehicle.device_sn,
                CONF_VEHICLE_MODEL: vehicle.model,
                CONF_VEHICLE_BRAND: vehicle.brand,
                CONF_VEHICLE_PLATE: vehicle.plate,
                CONF_VEHICLE_IMG_FRONT: vehicle.img_front,
                CONF_VEHICLE_IMG_SIDE: vehicle.img_side,
                CONF_VEHICLE_IMG_TOP: vehicle.img_top,
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

        current_scan = self._entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current_scan): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
