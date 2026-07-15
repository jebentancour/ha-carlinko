"""DataUpdateCoordinator: polls the CarLinko realtime WebSocket on a timer."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CarLinkoAuthError, CarLinkoClient, CarLinkoConnectionError
from .const import CONF_DEVICE_SN, CONF_SCAN_INTERVAL, CONF_VEHICLE_ID, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class CarLinkoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches + decodes one telemetry blob per update cycle."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: CarLinkoClient) -> None:
        self.client = client
        self.vehicle_id = entry.data[CONF_VEHICLE_ID]
        self.device_sn = entry.data[CONF_DEVICE_SN]
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.client.poll_telemetry(self.vehicle_id, self.device_sn)
        except CarLinkoAuthError as err:
            raise UpdateFailed(f"CarLinko login rejected: {err}") from err
        except CarLinkoConnectionError as err:
            raise UpdateFailed(f"Could not reach CarLinko: {err}") from err

        if data is None:
            # Car is offline (no signal) — keep last-known values, just flag it.
            previous = dict(self.data) if self.data else {}
            previous["online"] = False
            return previous

        data["online"] = True
        return data
