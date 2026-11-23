#!/usr/bin/env python3
"""setup_apple_home: one tidy HomeKit Bridge, driven through HA's own flows.

Runs the shipped apple_home.py without Home Assistant. The fake flow managers
follow the step order of homekit/config_flow.py in HA 2026.9.2:
  config flow : user -> pairing -> create_entry
  options flow: init -> include -> (cameras/climate) -> bridged_device_triggers -> create_entry
Checks:
  - only zone lights, mood switches and thermostats are selected; scenes,
    per-device lights and other integrations' entities are not;
  - include_moods/include_climate switch those groups off; lights always stay;
  - domains passed = only domains with selected entities (HomeKit would
    otherwise include a whole domain);
  - first run creates the bridge, second run updates the same one.

Run:  python3 tests/test_apple_home.py
"""
import asyncio
import enum
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


class FlowResultType(str, enum.Enum):
    FORM = "form"
    CREATE_ENTRY = "create_entry"
    ABORT = "abort"


REG = []          # fake entity registry rows
STORE = {}


class Store:
    def __init__(self, hass, version, key):
        self.key = key

    async def async_load(self):
        return STORE.get(self.key)

    async def async_save(self, data):
        STORE[self.key] = data


er = types.SimpleNamespace(
    async_get=lambda hass: None,
    async_entries_for_config_entry=lambda reg, eid: [r for r in REG if r.config_entry_id == eid],
)
for n in ["homeassistant", "homeassistant.helpers"]:
    stub(n)
stub("homeassistant.config_entries", SOURCE_USER="user")
stub("homeassistant.core", HomeAssistant=object)
stub("homeassistant.data_entry_flow", FlowResultType=FlowResultType)
sys.modules["homeassistant.helpers.entity_registry"] = er
sys.modules["homeassistant.helpers"].entity_registry = er
stub("homeassistant.helpers.storage", Store=Store)
pkg = types.ModuleType(PKG)
pkg.__path__ = [str(ROOT / PKG)]
sys.modules[PKG] = pkg
stub(f"{PKG}.const", DOMAIN="digitalstrom_smart")
ah = importlib.import_module(f"{PKG}.apple_home")


def row(entity_id, uid, eid="ds", disabled=None):
    return types.SimpleNamespace(
        entity_id=entity_id, domain=entity_id.split(".")[0], unique_id=uid,
        config_entry_id=eid, disabled_by=disabled,
    )


REG.extend([
    row("light.keuken", "ds_x_10_light"),
    row("light.gang", "ds_x_20_light"),
    row("light.oud", "ds_x_30_light", disabled="user"),
    row("light.spot_device", "ds_x_abc123_device_light"),
    row("switch.keuken_gezellig", "ds_x_10_mood_18"),
    row("switch.joker", "ds_x_10_joker_ab"),
    row("scene.keuken_dag", "ds_x_10_g1_scene_5"),
    row("climate.keuken", "ds_x_10_climate"),
    row("light.shelly", "shelly_1", eid="other"),
])


class Entry:
    def __init__(self, eid):
        self.entry_id = eid
        self.options = {}


class Hass:
    def __init__(self):
        self.entries = {}
        self.log = []
        hass = self

        class ConfigFlow:
            async def async_init(self, domain, context):
                hass.log.append(("init", domain, context["source"]))
                return {"type": FlowResultType.FORM, "step_id": "user", "flow_id": "c1"}

            async def async_configure(self, flow_id, data):
                hass.log.append(("cfg", flow_id, data))
                if "include_domains" in data:
                    hass.created_domains = data["include_domains"]
                    return {"type": FlowResultType.FORM, "step_id": "pairing", "flow_id": "c1"}
                e = Entry(f"hk{len(hass.entries) + 1}")
                hass.entries[e.entry_id] = e
                return {"type": FlowResultType.CREATE_ENTRY, "result": e}

        class OptionsFlow:
            order = ["init", "include", "climate", "bridged_device_triggers"]

            async def async_init(self, entry_id):
                self.entry_id, self.i, self.opts = entry_id, 0, {}
                return {"type": FlowResultType.FORM, "step_id": "init", "flow_id": "o1"}

            async def async_configure(self, flow_id, data):
                self.opts.update(data)
                self.i += 1
                if self.i < len(self.order):
                    return {"type": FlowResultType.FORM, "step_id": self.order[self.i], "flow_id": flow_id}
                hass.entries[self.entry_id].options = dict(self.opts)
                return {"type": FlowResultType.CREATE_ENTRY}

        self.config_entries = types.SimpleNamespace(
            flow=ConfigFlow(), options=OptionsFlow(),
            async_get_entry=lambda eid: self.entries.get(eid),
        )


def main():
    hass = Hass()
    s = asyncio.run(ah.async_setup_apple_home(hass, ["ds"]))
    assert s["created"] and s["lights"] == 2 and s["moods"] == 1 and s["thermostats"] == 1, s
    opts = hass.entries[s["homekit_entry_id"]].options
    assert opts["entities"] == ["climate.keuken", "light.gang", "light.keuken", "switch.keuken_gezellig"], opts
    assert opts["domains"] == ["climate", "light", "switch"] and opts["include_exclude_mode"] == "include"
    assert hass.created_domains == ["climate", "light", "switch"]

    # second run: same bridge, no new pairing; moods + thermostats off
    s2 = asyncio.run(ah.async_setup_apple_home(hass, ["ds"], include_climate=False, include_moods=False))
    assert not s2["created"] and s2["homekit_entry_id"] == s["homekit_entry_id"], s2
    assert len(hass.entries) == 1
    opts = hass.entries[s["homekit_entry_id"]].options
    assert opts["entities"] == ["light.gang", "light.keuken"] and opts["domains"] == ["light"], opts

    # bridge removed by the user: a new one is created
    hass.entries.clear()
    s3 = asyncio.run(ah.async_setup_apple_home(hass, ["ds"]))
    assert s3["created"]
    print("apple home: alle controles geslaagd")


if __name__ == "__main__":
    main()
