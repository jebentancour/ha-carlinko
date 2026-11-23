"""DataUpdateCoordinator: polls CarLinko telemetry (cloud and/or BLE) with an odometer freshness gate."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CarLinkoAuthError,
    CarLinkoClient,
    CarLinkoConnectionError,
    decode_control_config,
)
from .const import (
    CONF_BLE_ADDRESS,
    CONF_SCAN_INTERVAL,
    CONF_VEHICLE_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Largest odometer increase accepted between two readings; a bigger jump is treated as a corrupt
# frame rather than real distance, so it can't poison the freshness gate and freeze the sensors.
MAX_ODOMETER_JUMP_KM = 5000


class CarLinkoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Merges cloud + BLE telemetry each cycle, keeping only states no older than the last accepted."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: CarLinkoClient) -> None:
        self.client = client
        self.vehicle_id = entry.data[CONF_VEHICLE_ID]
        self._ble_address: str | None = entry.data.get(CONF_BLE_ADDRESS)
        # Highest odometer accepted so far: our rudimentary freshness clock (it only ever grows).
        self._last_odometer: int | None = None
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

    def _ble_present(self) -> bool:
        """Whether the car is currently in BLE range (i.e. 'home'). False if no BLE address known."""
        if not self._ble_address:
            return False
        return bluetooth.async_address_present(self.hass, self._ble_address, connectable=True)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            candidates = await self.client.poll_telemetry(self.vehicle_id)
        except CarLinkoAuthError as err:
            raise ConfigEntryAuthFailed(f"CarLinko login rejected: {err}") from err
        except CarLinkoConnectionError as err:
            raise UpdateFailed(f"Could not reach CarLinko: {err}") from err

        ble_present = self._ble_present()

        if not candidates:
            # No source responded: keep last-known values, just flag the car offline.
            previous = dict(self.data) if self.data else {}
            # Capability flags come from /user/vehicle, which answers even while the car is offline;
            # merge them so capability-dependent entities are still created on a first cold refresh.
            try:
                control_config = await self.client.get_vehicle_control_config(self.vehicle_id)
            except CarLinkoConnectionError as err:
                raise UpdateFailed(f"Could not reach CarLinko: {err}") from err
            previous.update(decode_control_config(control_config))
            previous["online"] = False
            previous["ble_present"] = ble_present
            return previous

        # Freshest candidate this cycle; on an odometer tie prefer BLE (the more local source).
        best = max(candidates, key=lambda c: ((c.get("odometer_km") or -1), c.get("source") == "ble"))
        odometer = best.get("odometer_km")

        if odometer is not None and self._last_odometer is not None and (
            odometer < self._last_odometer or odometer > self._last_odometer + MAX_ODOMETER_JUMP_KM
        ):
            # Older than what we already have (a stale cloud reply after driving out of BLE range),
            # or an implausibly large jump (a corrupt frame that slipped through): hold the last
            # values instead of jumping, and don't let the bad odometer poison the gate.
            held = dict(self.data) if self.data else {}
            held["online"] = True
            held["ble_present"] = ble_present
            return held

        if odometer is not None:
            self._last_odometer = odometer
        best["online"] = True
        best["data_source"] = best.get("source")
        best["ble_present"] = ble_present
        return best
