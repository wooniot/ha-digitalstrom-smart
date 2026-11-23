#!/usr/bin/env python3
"""Pro mood switches ("sfeerschakelaars") for Apple Home / voice.

Checks against the shipped switch.py, without Home Assistant (stub modules):
  - Free: no mood switches at all.
  - Pro: one switch per NAMED light scene of a zone; generic presets, off,
    deep-off and area-off scenes get none (tidy Apple Home).
  - is_on follows the zone's active light scene.
  - turn_on calls the scene, turn_off calls Off only when this mood is active.

Run:  python3 tests/test_mood_switch.py
"""
import asyncio
import importlib
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent / "custom_components"
PKG = "digitalstrom_smart"


def stub(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


class _Entity:
    def async_write_ha_state(self):
        pass


class CoordinatorEntity(_Entity):
    def __init__(self, coordinator):
        self.coordinator = coordinator


for n in ["homeassistant", "homeassistant.components", "homeassistant.helpers"]:
    stub(n)
stub("homeassistant.components.switch", SwitchEntity=_Entity)
stub("homeassistant.config_entries", ConfigEntry=object)
stub("homeassistant.core", HomeAssistant=object, callback=lambda f: f)
stub("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
stub("homeassistant.helpers.update_coordinator", CoordinatorEntity=CoordinatorEntity)
stub("homeassistant.const")

pkg = types.ModuleType(PKG)
pkg.__path__ = [str(ROOT / PKG)]
sys.modules[PKG] = pkg


class DigitalStromApiError(Exception):
    pass


stub(f"{PKG}.api", DigitalStromApiError=DigitalStromApiError)
stub(f"{PKG}.coordinator", DigitalStromCoordinator=object)
const = importlib.import_module(f"{PKG}.const")
switch = importlib.import_module(f"{PKG}.switch")

GL = const.GROUP_LIGHT


class Api:
    def __init__(self):
        self.calls = []

    async def call_scene(self, zone, group, scene, force=False):
        self.calls.append((zone, group, scene))


class Coord:
    def __init__(self, pro):
        self.pro_enabled = pro
        self.dss_id = "dss1"
        self.api = Api()
        self.zones = {
            10: {"name": "Keuken", "groups": [GL]},
            20: {"name": "Gang", "groups": [GL]},
            30: {"name": "Schuur", "groups": [8]},          # no light group
        }
        self.scene_names = {
            (10, GL, 0): "Uit",            # off: excluded
            (10, GL, 5): "Dag",
            (10, GL, 18): "Gezellig",
            (10, GL, 2): "Area 2 uit",     # area-off: excluded
            (10, GL, 68): "Diep uit",      # deep off: excluded
            (10, 2, 5): "Zonwering open",  # shade: excluded
            (30, GL, 5): "Werk",           # zone without light group
            (20, GL, 17): "",              # empty name: excluded
        }
        self.custom_states = {}
        self.states = {}
        self.updates = 0

    def get_joker_actuators_in_zone(self, zone):
        return []

    def get_zone_state(self, zone, group):
        return self.states.get((zone, group), {"scene": None})

    def set_zone_state(self, zone, group, **kw):
        self.states.setdefault((zone, group), {}).update(kw)

    def zone_on_after_scene(self, zone, group, scene):
        return scene != 0

    def async_update_listeners(self):
        self.updates += 1


def setup(pro):
    coord = Coord(pro)
    hass = types.SimpleNamespace(data={const.DOMAIN: {"e": {"coordinator": coord}}})
    entry = types.SimpleNamespace(entry_id="e", data={})
    out = []
    asyncio.run(switch.async_setup_entry(hass, entry, out.extend))
    moods = [e for e in out if isinstance(e, switch.DigitalStromMoodSwitch)]
    return coord, moods


def main():
    _, moods = setup(pro=False)
    assert moods == [], "Free must not create mood switches"

    coord, moods = setup(pro=True)
    names = sorted((m._zone_id, m._attr_name) for m in moods)
    assert names == [(10, "Dag"), (10, "Gezellig")], names

    gez = next(m for m in moods if m._attr_name == "Gezellig")
    dag = next(m for m in moods if m._attr_name == "Dag")
    assert not gez.is_on

    asyncio.run(gez.async_turn_on())
    assert coord.api.calls[-1] == (10, GL, 18)
    assert gez.is_on and not dag.is_on

    # off while another mood is active: nothing happens
    n = len(coord.api.calls)
    asyncio.run(dag.async_turn_off())
    assert len(coord.api.calls) == n

    asyncio.run(gez.async_turn_off())
    assert coord.api.calls[-1] == (10, GL, 0)
    assert not gez.is_on

    # a scene called elsewhere (wall button) turns the matching switch on
    coord.set_zone_state(10, GL, scene=5)
    assert dag.is_on and not gez.is_on
    assert len({m._attr_unique_id for m in moods}) == len(moods)
    print("mood switch: alle controles geslaagd")


if __name__ == "__main__":
    main()
