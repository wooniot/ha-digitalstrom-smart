"""Apartment presence mode select for Digital Strom. PRO feature.

Provides a select entity to read and set the apartment-wide presence state:
Present, Absent, Sleeping, Wakeup, Standby, Deep Off.
"""

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, APARTMENT_PRESENCE_SCENES
from .coordinator import DigitalStromCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Digital Strom presence mode select (PRO)."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DigitalStromCoordinator = data["coordinator"]

    if not coordinator.pro_enabled:
        return

    async_add_entities([DigitalStromPresenceSelect(coordinator)])


class DigitalStromPresenceSelect(CoordinatorEntity, SelectEntity):
    """Apartment presence mode: Present, Absent, Sleeping, etc."""

    _attr_has_entity_name = True
    _attr_name = "Presence Mode"
    _attr_icon = "mdi:home-account"

    def __init__(self, coordinator: DigitalStromCoordinator) -> None:
        super().__init__(coordinator)
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_apartment_presence"
        self._attr_options = list(APARTMENT_PRESENCE_SCENES.values())
        self._scene_to_name = APARTMENT_PRESENCE_SCENES
        self._name_to_scene = {v: k for k, v in APARTMENT_PRESENCE_SCENES.items()}
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Server",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    @property
    def current_option(self) -> str | None:
        scene = self.coordinator.apartment_presence
        if scene is not None:
            return self._scene_to_name.get(scene)
        return None

    async def async_select_option(self, option: str) -> None:
        scene_nr = self._name_to_scene.get(option)
        if scene_nr is not None:
            await self.coordinator.call_apartment_scene(scene_nr)
            self.coordinator.set_apartment_presence(scene_nr)
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
