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

    entities: list[ButtonEntity] = [
        DigitalStromUserActionButton(coordinator, action)
        for action in coordinator.user_actions
    ]
    if entities:
        _LOGGER.info("Adding %d User Defined Action buttons", len(entities))

    # One run-once button per Configurator timer
    timer_count = 0
    for tid, data in coordinator.timed_events.items():
        entities.append(DigitalStromTimerRunOnceButton(coordinator, tid, data))
        timer_count += 1
    if timer_count:
        _LOGGER.info("Adding %d Timer run-once buttons", timer_count)

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


class DigitalStromTimerRunOnceButton(CoordinatorEntity, ButtonEntity):
    """Run a Configurator timer immediately, once.

    Reads the timer's configured actions (zone-scene / device-scene) from
    the dSS property tree and executes them through the standard scene
    API — independent of the timer's enabled flag or scheduled time.
    Enabling/disabling the timer itself stays in the dSS Configurator.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:timer-play-outline"

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        event_id: str,
        data: dict,
    ) -> None:
        super().__init__(coordinator)
        self._event_id = event_id
        dss_id = coordinator.dss_id
        name = data.get("name", f"Timer {event_id}")
        self._attr_unique_id = f"ds_{dss_id}_timer_runonce_{event_id}"
        self._attr_name = f"Run {name}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Server",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.get_timed_event(self._event_id) or {}
        attrs = {
            "enabled_in_dss": data.get("enabled"),
            "time_base": data.get("time_base"),
            "offset_seconds": data.get("offset"),
            "recurrence_base": data.get("recurrence_base"),
            "timer_id": self._event_id,
        }
        if data.get("last_executed"):
            attrs["last_executed"] = data["last_executed"]
        return attrs

    async def async_press(self) -> None:
        try:
            executed = await self.coordinator.run_timer_once(self._event_id)
            _LOGGER.info(
                "Timer %s executed %d action(s) on demand",
                self._event_id, executed,
            )
        except DigitalStromApiError as err:
            _LOGGER.error(
                "Failed to run timer %s: %s", self._event_id, err,
            )
