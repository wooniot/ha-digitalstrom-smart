"""Stable platform choice for dSS user states (sensor vs binary_sensor).

Historically the platform (sensor or binary_sensor) was decided at every
startup from the *current* value of the state. A state that is 1/True one
moment and a text value the next therefore kept hopping between the two
platforms, leaving an orphaned (restored, unavailable) entity behind each
time. Both platforms share the same unique_id ds_{dss_id}_userstate_{name},
so a flip created a second entity in the other platform's registry.

This module pins the platform once and keeps it, by letting an existing
entity-registry entry win over the live value.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN


def user_state_uid(dss_id: str, state_name: str) -> str:
    """Build the (platform-independent) unique_id for a dSS user state."""
    safe = state_name.replace(".", "_").replace(" ", "_")
    return f"ds_{dss_id}_userstate_{safe}"


def is_binary_value(data: dict) -> bool:
    """Return True if a dSS state behaves as binary (active/inactive, 1/2)."""
    state = str(data.get("state", "")).lower()
    if state in ("active", "inactive"):
        return True
    value = data.get("value")
    return isinstance(value, bool) or (
        isinstance(value, (int, float)) and value in (1, 2)
    )


def user_state_platform(
    hass: HomeAssistant, dss_id: str, state_name: str, data: dict
) -> str:
    """Return 'binary_sensor' or 'sensor' for this user state, stable across restarts.

    An existing registry entry always wins over the live value, so a state can
    never switch domain again. If both exist (the old bug), binary_sensor is
    kept and the stray sensor entry is cleaned up.
    """
    reg = er.async_get(hass)
    uid = user_state_uid(dss_id, state_name)
    bin_id = reg.async_get_entity_id("binary_sensor", DOMAIN, uid)
    sen_id = reg.async_get_entity_id("sensor", DOMAIN, uid)
    if bin_id and sen_id:
        reg.async_remove(sen_id)
        return "binary_sensor"
    if bin_id:
        return "binary_sensor"
    if sen_id:
        return "sensor"
    return "binary_sensor" if is_binary_value(data) else "sensor"
