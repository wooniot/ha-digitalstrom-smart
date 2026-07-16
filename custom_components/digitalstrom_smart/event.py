"""Event entities for Digital Strom button / rocker presses.

Each dS pushbutton or EnOcean rocker (identified by functionID) becomes an
``event`` entity that fires when the physical button is pressed. Driven by the
dSS ``buttonClick`` event stream, delivered in real time through the coordinator
event loop — no polling.
"""

import logging

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BUTTON_CLICK_TYPE_NAMES,
    BUTTON_ELEMENT_NAMES,
    DOMAIN,
    MANUFACTURER,
    signal_button_event,
)
from .coordinator import DigitalStromCoordinator

_LOGGER = logging.getLogger(__name__)

# Every event type an entity may fire: each element prefix x each click-name
# suffix, plus a fallback for click types we do not map.
EVENT_TYPES: list[str] = [
    f"{element}_{name}"
    for element in dict.fromkeys(BUTTON_ELEMENT_NAMES.values())
    for name in dict.fromkeys(BUTTON_CLICK_TYPE_NAMES.values())
] + ["unknown"]


def _event_type(button_index: object, click_type: object) -> str:
    """Map a dSS (buttonIndex, clickType) pair to a stable HA event type."""
    try:
        element = BUTTON_ELEMENT_NAMES.get(int(button_index), "button")  # type: ignore[arg-type]
    except (TypeError, ValueError):
        element = "button"
    try:
        name = BUTTON_CLICK_TYPE_NAMES.get(int(click_type))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        name = None
    if name is None:
        return "unknown"
    return f"{element}_{name}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Digital Strom button event entities."""
    coordinator: DigitalStromCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [
        DigitalStromButtonEvent(coordinator, entry.entry_id, dsuid, dev)
        for dsuid, dev in coordinator.button_devices().items()
    ]
    if entities:
        _LOGGER.info("Adding %d Digital Strom button event entities", len(entities))
    async_add_entities(entities)


class DigitalStromButtonEvent(EventEntity):
    """A dS pushbutton / rocker exposed as a Home Assistant event entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_icon = "mdi:gesture-tap-button"
    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = EVENT_TYPES

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        entry_id: str,
        dsuid: str,
        dev: dict,
    ) -> None:
        self._entry_id = entry_id
        self._dsuid = dsuid.lower()
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_button_{dsuid}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, dsuid)},
            "name": dev.get("name") or dsuid,
            "manufacturer": MANUFACTURER,
            "model": dev.get("hw_info") or "Button",
            "via_device": (DOMAIN, f"{dss_id}_apartment"),
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to buttonClick events for this device."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_button_event(self._entry_id),
                self._handle_button_event,
            )
        )

    @callback
    def _handle_button_event(self, payload: dict) -> None:
        """Fire the HA event when a buttonClick for this device arrives."""
        if (payload.get("dsuid") or "").lower() != self._dsuid:
            return
        event_type = _event_type(payload.get("button_index"), payload.get("click_type"))
        self._trigger_event(
            event_type,
            {
                "button_index": payload.get("button_index"),
                "click_type": payload.get("click_type"),
            },
        )
        self.async_write_ha_state()
