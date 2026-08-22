"""Apartment presence mode select for Digital Strom. PRO feature.

Provides a select entity to read and set the apartment-wide presence state:
Present, Absent, Sleeping, Wakeup, Standby, Deep Off.
"""

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, APARTMENT_PRESENCE_KEYS
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


class DigitalStromPresenceSelect(CoordinatorEntity, RestoreEntity, SelectEntity):
    """Apartment presence mode: Present, Absent, Sleeping, etc."""

    _attr_has_entity_name = True
    _attr_translation_key = "presence_mode"
    _attr_icon = "mdi:home-account"

    def __init__(self, coordinator: DigitalStromCoordinator) -> None:
        super().__init__(coordinator)
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_apartment_presence"
        self._attr_options = list(APARTMENT_PRESENCE_KEYS.values())
        self._scene_to_key = APARTMENT_PRESENCE_KEYS
        self._key_to_scene = {v: k for k, v in APARTMENT_PRESENCE_KEYS.items()}
        self._restored_scene: int | None = None
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Server",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    async def async_added_to_hass(self) -> None:
        """Restore the last known presence after a (re)start.

        The dSS notification API only pushes presence on change, and after a
        restart getLastCalledScene(0,0) frequently returns a non-presence scene
        (esp. on larger installations), so the coordinator poll can't seed the
        value and the entity shows 'unknown' (issue #10/#33). Restoring the last
        known option keeps the state meaningful; a later event/poll overrides it
        with the live value.
        """
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in self._key_to_scene:
            self._restored_scene = self._key_to_scene[last.state]
            if self.coordinator.apartment_presence is None:
                self.coordinator.set_apartment_presence(self._restored_scene)

    @property
    def current_option(self) -> str | None:
        scene = self.coordinator.apartment_presence
        if scene is None:
            scene = self._restored_scene
        if scene is not None:
            return self._scene_to_key.get(scene)
        return None

    async def async_select_option(self, option: str) -> None:
        scene_nr = self._key_to_scene.get(option)
        if scene_nr is not None:
            await self.coordinator.call_apartment_scene(scene_nr)
            self.coordinator.set_apartment_presence(scene_nr)
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
