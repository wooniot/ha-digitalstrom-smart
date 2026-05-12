"""Button entities for Digital Strom.

Imports User Defined Actions from the dSS Configurator as HA buttons.
Each press raises the dSS event with the action's id, triggering the
configured sequence inside the dSS.
"""

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DigitalStromApiError
from .const import DOMAIN, MANUFACTURER
from .coordinator import DigitalStromCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Digital Strom buttons (User Defined Actions)."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DigitalStromCoordinator = data["coordinator"]

    entities = [
        DigitalStromUserActionButton(coordinator, action)
        for action in coordinator.user_actions
    ]
    if entities:
        _LOGGER.info("Adding %d User Defined Action buttons", len(entities))
    async_add_entities(entities)


class DigitalStromUserActionButton(CoordinatorEntity, ButtonEntity):
    """A dSS User Defined Action, triggered by raising the named event."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:gesture-tap-button"

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        action: dict,
    ) -> None:
        super().__init__(coordinator)
        self._action_id = action["id"]
        self._action_name = action["name"]
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_useraction_{self._action_id}"
        self._attr_name = self._action_name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Server",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    async def async_press(self) -> None:
        """Trigger this User Defined Action on the dSS.

        The dSS "system-addon-user-defined-actions" script subscribes to the
        ``highlevelevent`` system event and runs the action whose id matches
        the ``id`` parameter — raising the event with the action id as a plain
        event name does NOT execute the configured actions.
        """
        try:
            await self.coordinator.api.raise_event(
                "highlevelevent",
                parameter=f"id={self._action_id}",
            )
            _LOGGER.debug(
                "Triggered User Defined Action %s (%s)",
                self._action_id, self._action_name,
            )
        except DigitalStromApiError as err:
            _LOGGER.error(
                "Failed to trigger User Defined Action %s: %s",
                self._action_name, err,
            )
