"""Scene entities for Digital Strom zones.

Creates scenes for light, shade, and heating groups using
names imported from the dSS Configurator.
"""

import logging

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DigitalStromApiError
from .const import (
    DOMAIN,
    MANUFACTURER,
    GROUP_LIGHT,
    GROUP_SHADE,
    GROUP_HEATING,
    GROUP_NAMES,
    NAMED_SCENES,
    NAMED_SCENES_SHADE,
    GROUP_HEATING_SCENES,
    AREA_SCENE_NAMES,
    SCENE_TRANSLATION_KEYS,
    CONF_ENABLED_ZONES,
)
from .coordinator import DigitalStromCoordinator

_LOGGER = logging.getLogger(__name__)

# Which groups get scene entities — default scenes per group
DEFAULT_SCENE_GROUPS = {
    GROUP_LIGHT: NAMED_SCENES,
    GROUP_SHADE: NAMED_SCENES_SHADE,
    GROUP_HEATING: GROUP_HEATING_SCENES,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Digital Strom scenes.

    Free: Default preset scenes (0, 5, 17, 18, 19) per group.
    Pro:  All reachable scenes + area scenes (6-9, 10-14, 20-24, 30-34, 40-44)
          + user-defined scenes from dSS.
    """
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DigitalStromCoordinator = data["coordinator"]
    enabled_zones = entry.data.get(CONF_ENABLED_ZONES, [])

    entities = []
    for zone_id, zone_info in coordinator.zones.items():
        if enabled_zones and zone_id not in enabled_zones:
            continue
        for group_id, default_scenes in DEFAULT_SCENE_GROUPS.items():
            if group_id not in zone_info["groups"]:
                continue

            # Free: only default preset scenes (0, 5, 17, 18, 19)
            scene_numbers = set(default_scenes.keys())

            # Pro: add area scenes, reachable scenes, and user-defined scenes
            if coordinator.pro_enabled:
                reachable = coordinator.reachable_scenes.get((zone_id, group_id), [])
                scene_numbers.update(reachable)

                for key, name in coordinator.scene_names.items():
                    if key[0] == zone_id and key[1] == group_id and name:
                        scene_numbers.add(key[2])

            for scene_nr in sorted(scene_numbers):
                display_name = coordinator.get_scene_display_name(
                    zone_id, group_id, scene_nr
                )
                entities.append(
                    DigitalStromScene(
                        coordinator, zone_id, zone_info,
                        group_id, scene_nr, display_name,
                    )
                )

    async_add_entities(entities)


class DigitalStromScene(Scene):
    """A Digital Strom scene (primary automation method)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        zone_id: int,
        zone_info: dict,
        group: int,
        scene_number: int,
        scene_name: str,
    ) -> None:
        self._coordinator = coordinator
        self._zone_id = zone_id
        self._zone_name = zone_info["name"]
        self._group = group
        self._scene_number = scene_number
        dss_id = coordinator.dss_id
        group_label = GROUP_NAMES.get(group, f"G{group}")
        self._attr_unique_id = f"ds_{dss_id}_{zone_id}_g{group}_scene_{scene_number}"
        # Use translation_key for default scenes; custom-named scenes use
        # the name as-is (no English group prefix — zone device provides context).
        has_custom_name = (zone_id, group, scene_number) in coordinator.scene_names
        translation_key = SCENE_TRANSLATION_KEYS.get((group, scene_number))
        if not has_custom_name and translation_key:
            self._attr_translation_key = translation_key
        elif has_custom_name:
            self._attr_name = scene_name
        else:
            self._attr_name = f"{group_label} {scene_name}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": self._zone_name,
            "manufacturer": MANUFACTURER,
            "model": "Zone",
        }

    async def async_activate(self, **kwargs) -> None:
        """Activate the scene."""
        try:
            await self._coordinator.api.call_scene(
                self._zone_id, self._group, self._scene_number
            )
        except DigitalStromApiError as err:
            _LOGGER.error(
                "Failed to activate scene %s in zone %s: %s",
                self._scene_number,
                self._zone_name,
                err,
            )
