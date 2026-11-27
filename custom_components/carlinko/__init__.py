"""The CarLinko integration (Jaecoo / Omoda / Chery EVs on the CarLinko cloud, with optional BLE)."""
from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import ble
from .api import CarLinkoClient
from .ble import CarLinkoBleUnavailable
from .cloud import CarLinkoConnectionError
from .const import (
    CONF_BLE_ADDRESS,
    CONF_DEVICE_SN,
    CONF_REGION,
    CONF_TRANSPORT_MODE,
    CONF_USER_ID,
    CONF_VEHICLE_ID,
    CONF_VIN,
    DEFAULT_TRANSPORT_MODE,
    DOMAIN,
    TRANSPORT_CLOUD,
)
from .coordinator import CarLinkoCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.IMAGE,
    Platform.BUTTON,
    Platform.LOCK,
    Platform.COVER,
    Platform.SWITCH,
    Platform.FAN,
    Platform.CLIMATE,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    transport_mode = entry.options.get(CONF_TRANSPORT_MODE, DEFAULT_TRANSPORT_MODE)
    client = CarLinkoClient(
        session,
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_REGION],
        hass.config.time_zone,
        transport_mode=transport_mode,
        device_sn=entry.data[CONF_DEVICE_SN],
    )

    if transport_mode != TRANSPORT_CLOUD:
        await _setup_ble_transport(hass, entry, client)

    coordinator = CarLinkoCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _setup_ble_transport(hass: HomeAssistant, entry: ConfigEntry, client: CarLinkoClient) -> None:
    """Resolve VIN / userId / BLE address and wire the BLE transport onto the client.

    BLE telemetry and control both need the address, VIN and userId. Values are stored at
    config-flow time; existing entries are backfilled here once.
    """
    device_sn = entry.data[CONF_DEVICE_SN]
    vin = entry.data.get(CONF_VIN)
    user_id = entry.data.get(CONF_USER_ID)
    address = entry.data.get(CONF_BLE_ADDRESS)
    updates: dict[str, str] = {}

    if not vin:
        try:
            vehicles = await client.get_vehicles()
            match = next((v for v in vehicles if v.vehicle_id == entry.data[CONF_VEHICLE_ID]), None)
            vin = match.vin if match else ""
        except CarLinkoConnectionError:
            vin = ""
        if vin:
            updates[CONF_VIN] = vin

    if not user_id:
        try:
            user_id = await client.get_user_id()
            updates[CONF_USER_ID] = user_id
        except CarLinkoConnectionError:
            user_id = None

    if not address:
        address = _discover_address(hass, device_sn)
        if address:
            updates[CONF_BLE_ADDRESS] = address

    if updates:
        hass.config_entries.async_update_entry(entry, data={**entry.data, **updates})

    if not (vin and user_id):
        _LOGGER.warning(
            "CarLinko BLE enabled but VIN/userId could not be resolved and BLE needs both; "
            "BLE control will stay disabled until the next reload"
        )

    # Re-resolve the address at call time too, so BLE starts working once the car is first seen.
    addr_state = {"address": address}

    def _resolve_address() -> str | None:
        if addr_state["address"]:
            return addr_state["address"]
        addr_state["address"] = _discover_address(hass, device_sn)
        return addr_state["address"]

    async def _ble_read() -> tuple[str, str, str] | None:
        addr = _resolve_address()
        if not addr:
            return None
        return await ble.async_read_telemetry(hass, addr, device_sn)

    vehicle_id = entry.data[CONF_VEHICLE_ID]

    async def _get_remaining() -> int | None:
        # Authorization seconds left, fetched only if the car refuses with 0x44 (enrol needed).
        return await client.ble_auth_remaining(vehicle_id)

    async def _ble_send(opcode: str) -> str | None:
        addr = _resolve_address()
        if not addr:
            raise CarLinkoBleUnavailable("car not discovered over BLE")
        if not (vin and user_id):
            raise CarLinkoBleUnavailable("BLE control unavailable: missing VIN/userId")
        return await ble.async_send_control(hass, addr, device_sn, vin, user_id, opcode, _get_remaining)

    client.set_ble_transport(_ble_send, _ble_read)


def _discover_address(hass: HomeAssistant, device_sn: str) -> str | None:
    """Find the T-box's BLE address by its advertised local name (CHR + last 8 of deviceSn)."""
    name = ble.device_name_from_sn(device_sn)
    for info in bluetooth.async_discovered_service_info(hass, connectable=True):
        if info.name == name:
            return info.address
    return None


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
