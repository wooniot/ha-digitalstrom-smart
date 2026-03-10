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
    CONF_ENABLED_ZONES,
)
from .coordinator import DigitalStromCoordinator

_LOGGER = logging.getLogger(__name__)

# Which groups get scene entities
SCENE_GROUPS = {
    GROUP_LIGHT: NAMED_SCENES,
    GROUP_SHADE: NAMED_SCENES_SHADE,
    GROUP_HEATING: GROUP_HEATING_SCENES,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Digital Strom scenes."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DigitalStromCoordinator = data["coordinator"]
    enabled_zones = entry.data.get(CONF_ENABLED_ZONES, [])

    entities = []
    for zone_id, zone_info in coordinator.zones.items():
        if enabled_zones and zone_id not in enabled_zones:
            continue
        for group_id, default_scenes in SCENE_GROUPS.items():
            if group_id not in zone_info["groups"]:
                continue
            for scene_nr in default_scenes:
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
