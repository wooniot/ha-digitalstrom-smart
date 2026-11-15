#!/usr/bin/env python3
"""Zone light switched on by brightness (zone/setValue) must stay on in HA.

Since v4.2.6 the coordinator copies the dSS state zone.N.light into the light's
is_on (stateChange event and every /usr/states poll). The dSS derives that state
from scene calls only; zone/setValue changes the output but sends no event and
leaves zone.N.light at its previous value (captured on a dSS 1.19.13 with dSM12).
So light.turn_on with a brightness on a zone that was off turned the lamp on, HA
showed 'on', and the next /usr/states poll (main cycle, <= 30 s) read
zone.N.light=inactive and switched HA back to 'off' while the lamp stayed on.

Like test_integration_version.py this runs without Home Assistant: it takes the
SOURCE of the real methods from coordinator.py and light.py and runs them on
small stand-ins, so it tests the shipped code, not a copy.

Run:  python3 tests/test_zone_light_setvalue.py
      (DS_SOURCE_DIR=<dir with coordinator.py/light.py> to test another tree)
"""
import ast
import asyncio
import os
import pathlib
import re
import types

SRC = pathlib.Path(
    os.environ.get(
        "DS_SOURCE_DIR",
        pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "digitalstrom_smart",
    )
)

GROUP_LIGHT = 1
SCENE_OFF = 0
SCENE_MAX = 5
ZONE = 2107

NAMESPACE = {
    "GROUP_LIGHT": GROUP_LIGHT,
    "GROUP_JOKER": 8,
    "GROUP_VENTILATION": 10,
    "GROUP_HOME_VENTILATION": 64,
    "SCENE_OFF": SCENE_OFF,
    "SCENE_MAX": SCENE_MAX,
    "AREA_ON_SCENES": {6: 1, 7: 2, 8: 3, 9: 4},
    "AREA_OFF_SCENES": {1: 1, 2: 2, 3: 3, 4: 4},
    "PRESENCE_SCENE_NUMBERS": {67, 68, 69, 70, 71, 72},
    "ALARM_SCENE_NUMBERS": {65, 74, 75, 76, 77},
    "MAX_JOKER_SKIP_CYCLES": 3,
    "VENT_EVENT_REFRESH_DELAY": 3,
    "STATE_VALUE_ACTIVE": 1,
    "APARTMENT_SYSTEM_STATES": (),
    "APARTMENT_ENV_STATES": (),
    "MOTION_STATE_RE": re.compile(r"^zone\.(\d+)\.motion$"),
    "_ZONE_LIGHT_STATE": re.compile(r"^zone\.(\d+)\.light$"),
    "ATTR_BRIGHTNESS": "brightness",
    "Any": object,
    "callback": lambda f: f,
    "_LOGGER": types.SimpleNamespace(debug=lambda *a, **k: None, warning=lambda *a, **k: None),
}


def methods(filename, classname, names, optional=()):
    tree = ast.parse((SRC / filename).read_text(encoding="utf-8"))
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == classname)
    found = {}
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in (*names, *optional):
            ns = dict(NAMESPACE)
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(SRC / filename), "exec"), ns)
            found[node.name] = ns[node.name]
    missing = set(names) - set(found)
    assert not missing, f"{classname} in {filename} lacks {sorted(missing)}"
    return found


COORDINATOR_METHODS = [
    "get_zone_state", "set_zone_state", "zone_on_after_scene",
    "fetch_dss_states", "_process_event",
]
# Added by the fix; optional so the same test can be run against v4.2.6
# (DS_SOURCE_DIR=...) to show the failure it guards against.
COORDINATOR_OPTIONAL = ["note_zone_set_value", "clear_zone_set_value"]


class FakeApi:
    def __init__(self):
        self.calls = []
        self.usr_states = []

    async def set_value(self, zone, group, value):
        self.calls.append(("setValue", zone, group, value))

    async def call_scene(self, zone, group, scene):
        self.calls.append(("callScene", zone, group, scene))

    async def get_all_states(self):
        return list(self.usr_states)


async def _noop_refresh(self, *args):
    """Ventilation re-read scheduled by scene events; not part of this test."""


def make_coordinator():
    attrs = dict(methods("coordinator.py", "DigitalStromCoordinator", COORDINATOR_METHODS,
                         COORDINATOR_OPTIONAL))
    attrs.update(
        _is_tracked_state=lambda self, name: False,
        _find_custom_state_by_key=lambda self, *a, **k: None,
        async_update_listeners=lambda self: None,
        _norm_state=lambda self, v: v,
        _refresh_vent_group=_noop_refresh,
        _refresh_ventilation_zone=_noop_refresh,
    )
    coord = type("Coordinator", (), attrs)()
    coord.api = FakeApi()
    coord.zones = {ZONE: {"name": "Buero", "groups": [GROUP_LIGHT], "devices": ["d1"]}}
    coord._zone_states = {}
    coord._zone_areas_on = {}
    coord._zone_broadcast_on = {}
    coord._zone_value_on = set()
    coord._apartment_presence = None
    coord._apartment_alarms = set()
    coord._apartment_states = {}
    coord._user_states = {}
    coord.devices = {}
    coord.entry_id = "test"
    coord.hass = types.SimpleNamespace(async_create_task=lambda c: c.close())
    return coord


def make_light(coord):
    attrs = methods("light.py", "DigitalStromLight", ["async_turn_on", "async_turn_off"])
    light = type("Light", (), attrs)()
    light.coordinator = coord
    light._zone_id = ZONE
    light.async_write_ha_state = lambda: None
    return light


def is_on(coord):
    return coord.get_zone_state(ZONE, GROUP_LIGHT).get("is_on")


def scene_event(coord, zone, scene, group=GROUP_LIGHT):
    coord._process_event({"name": "callScene",
                          "properties": {"zoneID": zone, "groupID": group, "sceneID": scene}})


def light_state_event(coord, value):
    coord._process_event({"name": "stateChange",
                          "properties": {"statename": f"zone.{ZONE}.light", "state": value}})


def poll(coord, value):
    coord.api.usr_states = [{"name": f"zone.{ZONE}.light", "value": value}]
    asyncio.run(coord.fetch_dss_states())


def zone_off(coord, light):
    asyncio.run(light.async_turn_off())
    scene_event(coord, ZONE, SCENE_OFF)
    assert is_on(coord) is False


# --- the bug -----------------------------------------------------------------

def test_brightness_on_survives_stale_poll():
    """Reproduction of 15 Nov 2026: turn_on(brightness) after off, then the 30 s poll."""
    coord = make_coordinator(); light = make_light(coord)
    zone_off(coord, light)
    asyncio.run(light.async_turn_on(brightness=255))
    assert coord.api.calls[-1] == ("setValue", ZONE, GROUP_LIGHT, 255)
    assert is_on(coord) is True
    poll(coord, 2)  # dSS still reports zone.N.light inactive after setValue
    assert is_on(coord) is True, "stale zone.N.light=inactive switched the HA light off"


def test_brightness_on_survives_repeated_polls():
    coord = make_coordinator(); light = make_light(coord)
    zone_off(coord, light)
    asyncio.run(light.async_turn_on(brightness=128))
    for _ in range(3):
        poll(coord, 2)
    assert is_on(coord) is True, "stale zone.N.light=inactive switched the HA light off"


def test_active_event_then_inactive_event_is_off():
    """After setValue: dSS reports active (scene elsewhere), then inactive -> genuine off."""
    coord = make_coordinator(); light = make_light(coord)
    zone_off(coord, light)
    asyncio.run(light.async_turn_on(brightness=128))
    light_state_event(coord, "active")
    light_state_event(coord, "inactive")
    assert is_on(coord) is False


# --- what must keep working ----------------------------------------------------

def test_wall_switch_off_after_brightness_on():
    coord = make_coordinator(); light = make_light(coord)
    zone_off(coord, light)
    asyncio.run(light.async_turn_on(brightness=200))
    scene_event(coord, ZONE, SCENE_OFF)  # wall switch / dS app off
    assert is_on(coord) is False


def test_global_all_off_after_brightness_on():
    """Global 'all off' (v4.2.6-beta1/2): apartment scene + zone.N.light; no per-zone callScene."""
    coord = make_coordinator(); light = make_light(coord)
    zone_off(coord, light)
    asyncio.run(light.async_turn_on(brightness=200))
    scene_event(coord, 0, 72, group=0)  # apartment scene, e.g. absent / all off
    poll(coord, 2)
    assert is_on(coord) is False


def test_restart_seed_corrected_by_poll():
    """v4.2.6-beta2: seed from getLastCalledScene says on, zone.N.light says off -> off."""
    coord = make_coordinator()
    coord.set_zone_state(ZONE, GROUP_LIGHT, scene=SCENE_MAX, is_on=True)
    poll(coord, 2)
    assert is_on(coord) is False


def test_scene_on_then_inactive_event_is_off():
    coord = make_coordinator(); light = make_light(coord)
    asyncio.run(light.async_turn_on())
    assert coord.api.calls[-1] == ("callScene", ZONE, GROUP_LIGHT, SCENE_MAX)
    light_state_event(coord, "inactive")
    assert is_on(coord) is False


def test_active_state_rearms_inactive():
    """Once the dSS reports active again, a later inactive is genuine."""
    coord = make_coordinator(); light = make_light(coord)
    zone_off(coord, light)
    asyncio.run(light.async_turn_on(brightness=255))
    poll(coord, 1)
    poll(coord, 2)
    assert is_on(coord) is False


def test_zone_scene_clears_mark():
    """After a zone scene zone.N.light is authoritative again (no lingering mark)."""
    coord = make_coordinator(); light = make_light(coord)
    zone_off(coord, light)
    asyncio.run(light.async_turn_on(brightness=255))
    scene_event(coord, ZONE, 17)  # preset 2 from a wall button
    light_state_event(coord, "inactive")  # e.g. a later global off
    assert is_on(coord) is False


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as err:
                failed += 1
                print("FAIL", name, "-", str(err) or "assertion failed")
            except Exception as err:  # a crash in the code under test is a failure too
                failed += 1
                print("ERROR", name, "-", type(err).__name__, err)
    raise SystemExit(1 if failed else 0)
