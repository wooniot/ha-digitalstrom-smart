"""Switch entities for Digital Strom - individual Joker (black) device control."""

import asyncio
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DigitalStromApiError
from .const import DOMAIN, MANUFACTURER, GROUP_JOKER, CONF_ENABLED_ZONES, APARTMENT_ALARM_SCENES, SCENE_DOOR_BELL
from .coordinator import DigitalStromCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Digital Strom switches for individual Joker devices."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DigitalStromCoordinator = data["coordinator"]
    enabled_zones = entry.data.get(CONF_ENABLED_ZONES, [])

    entities = []

    for zone_id, zone_info in coordinator.zones.items():
        if enabled_zones and zone_id not in enabled_zones:
            continue
        if GROUP_JOKER not in zone_info["groups"]:
            continue

        # Create individual switch per Joker ACTUATOR in this zone
        # (sensors like contacts and smoke detectors go to binary_sensor)
        joker_devices = coordinator.get_joker_actuators_in_zone(zone_id)
        for dev in joker_devices:
            entities.append(
                DigitalStromJokerSwitch(coordinator, zone_id, zone_info, dev)
            )

    # --- PRO: Apartment alarm switches ---
    if coordinator.pro_enabled:
        for scene_nr, name in APARTMENT_ALARM_SCENES.items():
            entities.append(
                DigitalStromAlarmSwitch(coordinator, scene_nr, name)
            )

    async_add_entities(entities)


class DigitalStromAlarmSwitch(CoordinatorEntity, SwitchEntity):
    """Apartment alarm switch: Alarm 1-4, Panic. PRO."""

    _attr_has_entity_name = True

    _ICONS = {
        "Alarm 1": "mdi:alarm-light",
        "Alarm 2": "mdi:alarm-light-outline",
        "Alarm 3": "mdi:fire",
        "Alarm 4": "mdi:alert",
        "Panic": "mdi:alert-octagon",
        "Doorbell": "mdi:bell-ring",
    }

    def __init__(
        self, coordinator: DigitalStromCoordinator, scene_nr: int, name: str,
    ) -> None:
        super().__init__(coordinator)
        self._scene_nr = scene_nr
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_apartment_alarm_{scene_nr}"
        self._attr_name = name
        self._attr_icon = self._ICONS.get(name, "mdi:alarm-light")
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Server",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_alarm_active(self._scene_nr)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.call_apartment_scene(self._scene_nr)
        self.coordinator.apartment_alarms.add(self._scene_nr)
        self.async_write_ha_state()
        # Doorbell is a pulse — auto-reset after 3 seconds
        if self._scene_nr == SCENE_DOOR_BELL:
            await asyncio.sleep(3)
            self.coordinator.apartment_alarms.discard(self._scene_nr)
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.undo_apartment_scene(self._scene_nr)
        self.coordinator.apartment_alarms.discard(self._scene_nr)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromJokerSwitch(CoordinatorEntity, SwitchEntity):
    """A Digital Strom individual Joker (black) device switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        zone_id: int,
        zone_info: dict,
        device: dict,
    ) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._zone_name = zone_info["name"]
        self._dsuid = device["dsuid"]
        self._device_name = device.get("name", "")
        dss_id = coordinator.dss_id

        self._attr_unique_id = f"ds_{dss_id}_{self._dsuid}_joker_switch"
        self._attr_icon = "mdi:electric-switch"

        # Use device name from dS if available, otherwise generic
        if self._device_name:
            self._attr_name = self._device_name
        else:
            self._attr_name = "Switch"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": self._zone_name,
            "manufacturer": MANUFACTURER,
            "model": "Zone",
        }

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.get_device_on_state(self._dsuid)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on this individual Joker device."""
        try:
            await self.coordinator.api.device_turn_on(self._dsuid)
            self.coordinator.set_device_on_state(self._dsuid, True)
            self.async_write_ha_state()
        except DigitalStromApiError as err:
            _LOGGER.error(
                "Failed to turn on %s (%s): %s",
                self._device_name or "switch", self._dsuid[:8], err,
            )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off this individual Joker device."""
        try:
            await self.coordinator.api.device_turn_off(self._dsuid)
            self.coordinator.set_device_on_state(self._dsuid, False)
            self.async_write_ha_state()
        except DigitalStromApiError as err:
            _LOGGER.error(
                "Failed to turn off %s (%s): %s",
                self._device_name or "switch", self._dsuid[:8], err,
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
