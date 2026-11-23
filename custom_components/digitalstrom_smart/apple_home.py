"""Apple Home in one step (Pro): a tidy HomeKit Bridge for Digital Strom.

Service digitalstrom_smart.setup_apple_home creates (or updates) ONE HomeKit
Bridge that contains only what is useful in the Apple Home app:
  - the zone light per room (on/off/dim, real state);
  - the mood switches per room (named dS scenes with real state, switch.py);
  - optionally the room thermostats (climate, Pro).
No scene buttons, no per-device entities: Apple Home stays clear
(Marijn, 23 nov 2026: "geen stortvloed aan knoppen").

It drives Home Assistant's own HomeKit config and options flows, exactly as a
user would in the UI, so nothing HomeKit-internal is touched. The first run
creates the bridge and HA shows the usual pairing QR code as a notification.
Later runs only update the entity list of that same bridge (no re-pairing).
Rooms are assigned in the Apple Home app; HomeKit does not carry rooms.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

HOMEKIT = "homekit"
_STORE_KEY = f"{DOMAIN}_apple_home"
_ZONE_LIGHT = re.compile(r"^ds_.+_\d+_light$")
_MOOD = re.compile(r"^ds_.+_\d+_mood_\d+$")
_CLIMATE = re.compile(r"^ds_.+_\d+_climate$")
_MAX_STEPS = 12


def select_entities(
    hass: HomeAssistant,
    ds_entry_ids: list[str],
    include_climate: bool,
    include_moods: bool = True,
) -> list[str]:
    """Entity ids of zone lights, mood switches and (optionally) thermostats."""
    reg = er.async_get(hass)
    out: list[str] = []
    for entry_id in ds_entry_ids:
        for ent in er.async_entries_for_config_entry(reg, entry_id):
            if ent.disabled_by is not None:
                continue
            uid = ent.unique_id or ""
            if ent.domain == "light" and _ZONE_LIGHT.match(uid):
                out.append(ent.entity_id)
            elif include_moods and ent.domain == "switch" and _MOOD.match(uid):
                out.append(ent.entity_id)
            elif include_climate and ent.domain == "climate" and _CLIMATE.match(uid):
                out.append(ent.entity_id)
    return sorted(out)


async def _drive(hass: HomeAssistant, manager, result: dict, answers: dict) -> dict:
    """Walk a flow; known steps get our answer, others their defaults."""
    for _ in range(_MAX_STEPS):
        if result["type"] != FlowResultType.FORM:
            return result
        step = result["step_id"]
        result = await manager.async_configure(result["flow_id"], answers.get(step, {}))
    raise RuntimeError(f"HomeKit flow did not finish (last step {result.get('step_id')})")


async def _create_bridge(hass: HomeAssistant, domains: list[str]) -> str:
    flow = hass.config_entries.flow
    result = await flow.async_init(HOMEKIT, context={"source": SOURCE_USER})
    result = await _drive(
        hass, flow, result, {"user": {"include_domains": domains}, "pairing": {}}
    )
    if result["type"] != FlowResultType.CREATE_ENTRY:
        raise RuntimeError(f"HomeKit bridge not created: {result.get('reason') or result['type']}")
    return result["result"].entry_id


async def _set_entities(
    hass: HomeAssistant, hk_entry_id: str, domains: list[str], entities: list[str]
) -> None:
    opts = hass.config_entries.options
    result = await opts.async_init(hk_entry_id)
    result = await _drive(
        hass,
        opts,
        result,
        {
            "init": {
                "mode": "bridge",
                "include_exclude_mode": "include",
                "domains": domains,
            },
            "include": {"entities": entities},
        },
    )
    if result["type"] != FlowResultType.CREATE_ENTRY:
        raise RuntimeError(f"HomeKit options not saved: {result['type']}")


async def async_setup_apple_home(
    hass: HomeAssistant,
    ds_entry_ids: list[str],
    include_climate: bool = True,
    include_moods: bool = True,
) -> dict[str, Any]:
    """Create or update the Digital Strom HomeKit Bridge. Returns a summary.

    The zone light per room (on/off/dim) is always included."""
    entities = select_entities(hass, ds_entry_ids, include_climate, include_moods)
    if not entities:
        raise RuntimeError("No Digital Strom zone lights found to bridge")
    # Only domains that have selected entities: HomeKit includes a domain
    # completely when none of its entities is listed.
    domains = sorted({e.split(".", 1)[0] for e in entities})

    store = Store(hass, 1, _STORE_KEY)
    saved = await store.async_load() or {}
    hk_entry_id = saved.get("homekit_entry_id")
    created = False
    if not hk_entry_id or hass.config_entries.async_get_entry(hk_entry_id) is None:
        hk_entry_id = await _create_bridge(hass, domains)
        created = True
        await store.async_save({"homekit_entry_id": hk_entry_id})

    await _set_entities(hass, hk_entry_id, domains, entities)
    summary = {
        "homekit_entry_id": hk_entry_id,
        "created": created,
        "entities": len(entities),
        "lights": sum(e.startswith("light.") for e in entities),
        "moods": sum(e.startswith("switch.") for e in entities),
        "thermostats": sum(e.startswith("climate.") for e in entities),
    }
    _LOGGER.info("Apple Home bridge %s: %s", "created" if created else "updated", summary)
    return summary
