"""Static vehicle photo entities (front/side/top) for the CarLinko integration.

URLs come from vehicleImgConfig in the /user/vehicle response, captured once at config-flow
time (see api.py get_vehicles()). They don't change between polls, so these aren't tied to
the coordinator — the image platform's own async_image()/image_url plumbing (via ImageEntity)
handles fetching and caching.
"""
from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DEVICE_SN,
    CONF_VEHICLE_BRAND,
    CONF_VEHICLE_ID,
    CONF_VEHICLE_IMG_FRONT,
    CONF_VEHICLE_IMG_SIDE,
    CONF_VEHICLE_IMG_TOP,
    CONF_VEHICLE_MODEL,
    CONF_VEHICLE_PLATE,
    DOMAIN,
)

IMAGES: tuple[tuple[str, str], ...] = (
    ("front", CONF_VEHICLE_IMG_FRONT),
    ("side", CONF_VEHICLE_IMG_SIDE),
    ("top", CONF_VEHICLE_IMG_TOP),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(CarLinkoImage(hass, entry, key, conf_key) for key, conf_key in IMAGES)


class CarLinkoImage(ImageEntity):
    _attr_has_entity_name = True
    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, key: str, conf_key: str) -> None:
        super().__init__(hass)
        self._entry = entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_image_{key}"
        self._attr_image_url = entry.data[conf_key]

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.data[CONF_VEHICLE_ID])},
            name=self._entry.data[CONF_VEHICLE_PLATE],
            manufacturer=self._entry.data[CONF_VEHICLE_BRAND],
            model=self._entry.data[CONF_VEHICLE_MODEL],
            serial_number=self._entry.data[CONF_DEVICE_SN],
        )
