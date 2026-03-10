"""Switch entities for Digital Strom (pause/resume + optional devices)."""

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import DigitalStromCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Digital Strom switches."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DigitalStromCoordinator = data["coordinator"]

    entities = [DigitalStromPauseSwitch(coordinator)]
    async_add_entities(entities)


class DigitalStromPauseSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to pause/resume all dSS communication.

    When ON = communication is PAUSED (for dS Configurator use).
    When OFF = normal operation.
    """

    _attr_has_entity_name = True
    _attr_name = "dSS Pause Communication"
    _attr_icon = "mdi:pause-circle-outline"

    def __init__(self, coordinator: DigitalStromCoordinator) -> None:
        super().__init__(coordinator)
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_pause_switch"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Apartment",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_paused

    @property
    def icon(self) -> str:
        if self.coordinator.is_paused:
            return "mdi:pause-circle"
        return "mdi:play-circle-outline"

    async def async_turn_on(self, **kwargs) -> None:
        """Pause communication."""
        await self.coordinator.pause()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Resume communication."""
        await self.coordinator.resume()
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
