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

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, SKIP_USER_STATES

_LOGGER = logging.getLogger(__name__)


def user_state_uid(dss_id: str, state_name: str) -> str:
    """Build the (platform-independent) unique_id for a dSS user state."""
    safe = state_name.replace(".", "_").replace(" ", "_")
    return f"ds_{dss_id}_userstate_{safe}"


def cleanup_skipped_user_states(hass: HomeAssistant, dss_id: str) -> int:
    """Remove stale user-state registry entries for names in SKIP_USER_STATES.

    Names in SKIP_USER_STATES are never imported as user states (they are
    exposed through dedicated entities, e.g. daynight/twilight/daylight/holiday
    as the fixed APARTMENT_ENV_STATES binary_sensors). But a name that only
    moved into SKIP_USER_STATES later leaves its old
    ds_{dss_id}_userstate_{name} registration behind as an orphaned (restored,
    unavailable) entity — in either platform. The duplicate-cleanup in
    user_state_platform() never fires for them, because they are skipped before
    any platform is asked for them.

    Run once per setup: drop both the sensor and binary_sensor registry entry
    for every skipped name. Idempotent — after the first run there is nothing
    left to remove. Safe because these names are never meant to exist as a user
    state; only the dedicated entities (different unique_id) remain.
    """
    reg = er.async_get(hass)
    removed = 0
    for name in SKIP_USER_STATES:
        uid = user_state_uid(dss_id, name)
        for platform in ("sensor", "binary_sensor"):
            ent_id = reg.async_get_entity_id(platform, DOMAIN, uid)
            if ent_id:
                reg.async_remove(ent_id)
                removed += 1
                _LOGGER.info(
                    "Removed stale user-state entity %s (%s, skipped name %r)",
                    ent_id, uid, name,
                )
    if removed:
        _LOGGER.info(
            "Cleaned up %d stale user-state registration(s) for skipped names",
            removed,
        )
    return removed


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
