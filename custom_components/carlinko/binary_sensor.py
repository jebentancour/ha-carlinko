"""Binary sensors for the CarLinko integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_SN, CONF_VEHICLE_BRAND, CONF_VEHICLE_ID, CONF_VEHICLE_MODEL, CONF_VEHICLE_PLATE, DOMAIN
from .coordinator import CarLinkoCoordinator


@dataclass(frozen=True, kw_only=True)
class CarLinkoBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any] = lambda data: None


BINARY_SENSORS: tuple[CarLinkoBinarySensorDescription, ...] = (
    CarLinkoBinarySensorDescription(
        key="lock",
        translation_key="lock",
        device_class=BinarySensorDeviceClass.LOCK,
        value_fn=lambda d: d.get("lock_unlocked"),
    ),
    CarLinkoBinarySensorDescription(
        key="door_front_left",
        translation_key="door_front_left",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: d.get("door_front_left"),
    ),
    CarLinkoBinarySensorDescription(
        key="door_front_right",
        translation_key="door_front_right",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: d.get("door_front_right"),
    ),
    CarLinkoBinarySensorDescription(
        key="door_rear_left",
        translation_key="door_rear_left",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: d.get("door_rear_left"),
    ),
    CarLinkoBinarySensorDescription(
        key="door_rear_right",
        translation_key="door_rear_right",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: d.get("door_rear_right"),
    ),
    CarLinkoBinarySensorDescription(
        key="window_front_left",
        translation_key="window_front_left",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=lambda d: d.get("window_front_left"),
    ),
    CarLinkoBinarySensorDescription(
        key="window_front_right",
        translation_key="window_front_right",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=lambda d: d.get("window_front_right"),
    ),
    CarLinkoBinarySensorDescription(
        key="window_rear_left",
        translation_key="window_rear_left",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=lambda d: d.get("window_rear_left"),
    ),
    CarLinkoBinarySensorDescription(
        key="window_rear_right",
        translation_key="window_rear_right",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=lambda d: d.get("window_rear_right"),
    ),
    CarLinkoBinarySensorDescription(
        key="trunk_open",
        translation_key="trunk_open",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: d.get("trunk_open"),
    ),
    CarLinkoBinarySensorDescription(
        key="ignition",
        translation_key="ignition",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda d: d.get("ignition_on"),
    ),
    CarLinkoBinarySensorDescription(
        key="sunroof_open",
        translation_key="sunroof_open",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=lambda d: d.get("sunroof_open"),
    ),
    CarLinkoBinarySensorDescription(
        key="ac_on",
        translation_key="ac_on",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda d: d.get("ac_on"),
    ),
    CarLinkoBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: d.get("charging"),
    ),
    CarLinkoBinarySensorDescription(
        key="defrost_front",
        translation_key="defrost_front",
        icon="mdi:car-defrost-front",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda d: d.get("defrost_front"),
    ),
)


CONTROL_CAPABILITY_SENSORS: tuple[CarLinkoBinarySensorDescription, ...] = (
    CarLinkoBinarySensorDescription(
        key="control_lock",
        translation_key="control_lock",
        icon="mdi:lock",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_lock"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_windows_open",
        translation_key="control_windows_open",
        icon="mdi:arrow-expand-vertical",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_windows_open"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_windows_close",
        translation_key="control_windows_close",
        icon="mdi:arrow-collapse-vertical",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_windows_close"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_windows_vent",
        translation_key="control_windows_vent",
        icon="mdi:window-open-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_windows_vent"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_sunroof",
        translation_key="control_sunroof",
        icon="mdi:car-convertible",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_sunroof"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_sunroof_tilt",
        translation_key="control_sunroof_tilt",
        icon="mdi:car-convertible",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_sunroof_tilt"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_liftgate",
        translation_key="control_liftgate",
        icon="mdi:car-back",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_liftgate"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_trunk",
        translation_key="control_trunk",
        icon="mdi:car-back",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_trunk"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_find",
        translation_key="control_find",
        icon="mdi:map-marker",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_find"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_charging_management",
        translation_key="control_charging_management",
        icon="mdi:ev-station",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_charging_management"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_switch",
        translation_key="control_ac_switch",
        icon="mdi:air-conditioner",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_switch"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_set_temperature",
        translation_key="control_ac_set_temperature",
        icon="mdi:thermostat",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_set_temperature"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_rapid_cool",
        translation_key="control_ac_rapid_cool",
        icon="mdi:snowflake",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_rapid_cool"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_rapid_heat",
        translation_key="control_ac_rapid_heat",
        icon="mdi:fire",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_rapid_heat"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_defog",
        translation_key="control_ac_defog",
        icon="mdi:car-defrost-front",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_defog"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_scheduled_charging",
        translation_key="control_scheduled_charging",
        icon="mdi:calendar-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_scheduled_charging"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_scheduled_travel",
        translation_key="control_scheduled_travel",
        icon="mdi:calendar-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_scheduled_travel"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_steering_wheel_heater",
        translation_key="control_steering_wheel_heater",
        icon="mdi:steering",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_steering_wheel_heater"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_front_windshield_heater",
        translation_key="control_front_windshield_heater",
        icon="mdi:car-defrost-front",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_front_windshield_heater"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_charging_power",
        translation_key="control_charging_power",
        icon="mdi:ev-station",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_charging_power"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_air_purification",
        translation_key="control_ac_air_purification",
        icon="mdi:air-filter",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_air_purification"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_driver_vent",
        translation_key="control_ac_driver_vent",
        icon="mdi:car-seat-cooler",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_driver_vent"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_assistant_vent",
        translation_key="control_ac_assistant_vent",
        icon="mdi:car-seat-cooler",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_assistant_vent"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_driver_heater",
        translation_key="control_ac_driver_heater",
        icon="mdi:car-seat-heater",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_driver_heater"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_assistant_heater",
        translation_key="control_ac_assistant_heater",
        icon="mdi:car-seat-heater",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_assistant_heater"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_rear_heater",
        translation_key="control_ac_rear_heater",
        icon="mdi:car-seat-heater",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_rear_heater"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_high_low_gear",
        translation_key="control_ac_high_low_gear",
        icon="mdi:fan",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_high_low_gear"),
    ),
    CarLinkoBinarySensorDescription(
        key="control_ac_set_duration",
        translation_key="control_ac_set_duration",
        icon="mdi:timer-cog-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("control_ac_set_duration"),
    ),
)


# From `/user/device/manage/terminalNoticeConfig/{id}` (api.decode_notice_config) — trip/charge
# schedules and per-event notification prefs. All diagnostic; keys share a prefix per
# section (trip_schedule_/charge_schedule_/notify_) so they group together in the UI.
NOTICE_CONFIG_BINARY_SENSORS: tuple[CarLinkoBinarySensorDescription, ...] = (
    CarLinkoBinarySensorDescription(
        key="trip_schedule_enabled",
        translation_key="trip_schedule_enabled",
        icon="mdi:calendar-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("trip_schedule_enabled"),
    ),
    CarLinkoBinarySensorDescription(
        key="charge_schedule_enabled",
        translation_key="charge_schedule_enabled",
        icon="mdi:calendar-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("charge_schedule_enabled"),
    ),
    CarLinkoBinarySensorDescription(
        key="notify_remote_startup",
        translation_key="notify_remote_startup",
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("notify_remote_startup"),
    ),
    CarLinkoBinarySensorDescription(
        key="notify_shutdown",
        translation_key="notify_shutdown",
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("notify_shutdown"),
    ),
    CarLinkoBinarySensorDescription(
        key="notify_locked",
        translation_key="notify_locked",
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("notify_locked"),
    ),
    CarLinkoBinarySensorDescription(
        key="notify_unlocked",
        translation_key="notify_unlocked",
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("notify_unlocked"),
    ),
    CarLinkoBinarySensorDescription(
        key="notify_trunk_opened",
        translation_key="notify_trunk_opened",
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("notify_trunk_opened"),
    ),
    CarLinkoBinarySensorDescription(
        key="notify_low_voltage",
        translation_key="notify_low_voltage",
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("notify_low_voltage"),
    ),
    CarLinkoBinarySensorDescription(
        key="notify_shaken",
        translation_key="notify_shaken",
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("notify_shaken"),
    ),
    CarLinkoBinarySensorDescription(
        key="notify_illegal_opened",
        translation_key="notify_illegal_opened",
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("notify_illegal_opened"),
    ),
    CarLinkoBinarySensorDescription(
        key="notify_illegal_startup",
        translation_key="notify_illegal_startup",
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("notify_illegal_startup"),
    ),
    CarLinkoBinarySensorDescription(
        key="notify_forget_to_lock",
        translation_key="notify_forget_to_lock",
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("notify_forget_to_lock"),
    ),
    CarLinkoBinarySensorDescription(
        key="notify_vehicle_immobilizer",
        translation_key="notify_vehicle_immobilizer",
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("notify_vehicle_immobilizer"),
    ),
    CarLinkoBinarySensorDescription(
        key="notify_vehicle_anomaly",
        translation_key="notify_vehicle_anomaly",
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("notify_vehicle_anomaly"),
    ),
    CarLinkoBinarySensorDescription(
        key="notify_battery_anomaly",
        translation_key="notify_battery_anomaly",
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("notify_battery_anomaly"),
    ),
    CarLinkoBinarySensorDescription(
        key="notify_charge_idle",
        translation_key="notify_charge_idle",
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("notify_charge_idle"),
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: CarLinkoCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [CarLinkoOnlineSensor(coordinator, entry)]
    entities += [CarLinkoBinarySensor(coordinator, entry, desc) for desc in BINARY_SENSORS]
    entities += [CarLinkoBinarySensor(coordinator, entry, desc) for desc in CONTROL_CAPABILITY_SENSORS]
    entities += [CarLinkoBinarySensor(coordinator, entry, desc) for desc in NOTICE_CONFIG_BINARY_SENSORS]
    async_add_entities(entities)


class _CarLinkoBinaryBase(CoordinatorEntity[CarLinkoCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.data[CONF_VEHICLE_ID])},
            name=self._entry.data[CONF_VEHICLE_PLATE],
            manufacturer=self._entry.data[CONF_VEHICLE_BRAND],
            model=self._entry.data[CONF_VEHICLE_MODEL],
            serial_number=self._entry.data[CONF_DEVICE_SN],
        )


class CarLinkoOnlineSensor(_CarLinkoBinaryBase):
    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: CarLinkoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_online"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return bool(self.coordinator.data.get("online"))


class CarLinkoBinarySensor(_CarLinkoBinaryBase):
    entity_description: CarLinkoBinarySensorDescription

    def __init__(
        self, coordinator: CarLinkoCoordinator, entry: ConfigEntry, description: CarLinkoBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.data[CONF_VEHICLE_ID]}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
