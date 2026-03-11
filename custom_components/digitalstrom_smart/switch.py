"""Switch entities for Digital Strom - individual Joker (black) device control."""

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DigitalStromApiError
from .const import DOMAIN, MANUFACTURER, GROUP_JOKER, CONF_ENABLED_ZONES
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

        # Create individual switch per Joker device in this zone
        joker_devices = coordinator.get_joker_devices_in_zone(zone_id)
        for dev in joker_devices:
            entities.append(
                DigitalStromJokerSwitch(coordinator, zone_id, zone_info, dev)
            )

    async_add_entities(entities)


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
