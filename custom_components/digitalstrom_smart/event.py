"""Event entities for Digital Strom button / rocker presses.

Every dS pushbutton or EnOcean rocker becomes an ``event`` entity that fires
when the physical button is pressed, driven by the dSS ``buttonClick`` event
stream (real time, via the coordinator event loop — no polling).

Discovery is twofold:
  * up front, devices whose dSS functionID marks them as a rocker/button
    (``BUTTON_FUNCTION_IDS``) so their entities exist immediately after start,
    plus any button entity already in the registry from a previous run;
  * dynamically, the first time a ``buttonClick`` arrives for a device we have
    not seen yet — this covers every other dS pushbutton type automatically
    without maintaining a functionID allow-list.
"""

import logging

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
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

_UNIQUE_PREFIX = "button_"

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
    dss_id = coordinator.dss_id
    uid_prefix = f"ds_{dss_id}_{_UNIQUE_PREFIX}"
    known: set[str] = set()

    def _make(dsuid: str, initial: dict | None = None) -> "DigitalStromButtonEvent":
        known.add(dsuid.lower())
        dev = coordinator.devices.get(dsuid) or coordinator.devices.get(dsuid.lower()) or {}
        return DigitalStromButtonEvent(coordinator, entry.entry_id, dsuid, dev, initial)

    entities: list[DigitalStromButtonEvent] = []

    # 1. Up-front: devices whose functionID marks them as a button/rocker.
    for dsuid in coordinator.button_devices():
        entities.append(_make(dsuid))

    # 2. Restore any button entity discovered on a previous run so it survives a
    #    restart before its next press.
    ent_reg = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if entity.domain == "event" and entity.unique_id.startswith(uid_prefix):
            dsuid = entity.unique_id[len(uid_prefix):]
            if dsuid.lower() not in known:
                entities.append(_make(dsuid))

    if entities:
        _LOGGER.info("Adding %d Digital Strom button event entities", len(entities))
    async_add_entities(entities)

    # 3. Dynamic discovery: first buttonClick from an unknown device -> new entity.
    @callback
    def _discover(payload: dict) -> None:
        raw = payload.get("dsuid") or ""
        if not raw or raw.lower() in known:
            return
        _LOGGER.info(
            "Discovered new Digital Strom button device %s (%s)",
            raw, (coordinator.devices.get(raw) or {}).get("name") or "?",
        )
        async_add_entities([_make(raw, initial=payload)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_button_event(entry.entry_id), _discover)
    )


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
        initial: dict | None = None,
    ) -> None:
        self._entry_id = entry_id
        self._dsuid = dsuid.lower()
        self._initial = initial
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_{_UNIQUE_PREFIX}{dsuid}"
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
        # If this entity was created by the dynamic-discovery press, fire that
        # first event now (it arrived before we were listening).
        if self._initial is not None:
            initial, self._initial = self._initial, None
            self._handle_button_event(initial)

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
