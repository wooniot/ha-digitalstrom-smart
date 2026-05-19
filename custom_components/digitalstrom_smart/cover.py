"""Zone-based cover entities for Digital Strom.

Supports position inversion for installations where the motor
direction is reversed (common with external blinds/screens).
"""

import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    GROUP_SHADE,
    SCENE_COVER_OPEN,
    SCENE_COVER_CLOSE,
    SCENE_COVER_STOP,
    SCENE_OFF,
    CONF_ENABLED_ZONES,
    CONF_INVERT_COVER,
)
from .coordinator import DigitalStromCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Digital Strom covers."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DigitalStromCoordinator = data["coordinator"]
    enabled_zones = entry.data.get(CONF_ENABLED_ZONES, [])
    invert = entry.options.get(CONF_INVERT_COVER, False)

    entities = []
    for zone_id, zone_info in coordinator.zones.items():
        if enabled_zones and zone_id not in enabled_zones:
            continue
        if GROUP_SHADE in zone_info["groups"]:
            entities.append(
                DigitalStromCover(coordinator, zone_id, zone_info, invert)
            )

    async_add_entities(entities)


class DigitalStromCover(CoordinatorEntity, CoverEntity):
    """A Digital Strom zone cover (blinds/shades).

    When invert_position is True:
    - dS 0 (closed) maps to HA 100 (open) and vice versa
    - Open/Close scene commands are swapped
    This handles installations where the motor direction is reversed.
    """

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.SHADE
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        zone_id: int,
        zone_info: dict,
        invert: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._zone_name = zone_info["name"]
        self._invert = invert
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_{zone_id}_cover"
        self._attr_translation_key = "zone_cover"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": self._zone_name,
            "manufacturer": MANUFACTURER,
            "model": "Zone",
        }

    def _ds_to_ha_position(self, ds_value: int) -> int:
        """Convert dS value (0-255) to HA position (0-100).

        Normal: dS 0=closed → HA 0, dS 255=open → HA 100
        Inverted: dS 0=closed → HA 100, dS 255=open → HA 0
        """
        ha_pos = round(ds_value * 100 / 255)
        if self._invert:
            ha_pos = 100 - ha_pos
        return ha_pos

    def _ha_to_ds_value(self, ha_position: int) -> int:
        """Convert HA position (0-100) to dS value (0-255)."""
        if self._invert:
            ha_position = 100 - ha_position
        return round(ha_position * 255 / 100)

    # Available is handled by CoordinatorEntity base class

    @property
    def current_cover_position(self) -> int | None:
        state = self.coordinator.get_zone_state(self._zone_id, GROUP_SHADE)
        value = state.get("value")
        if value is not None:
            return self._ds_to_ha_position(value)
        return None

    @property
    def is_closed(self) -> bool | None:
        state = self.coordinator.get_zone_state(self._zone_id, GROUP_SHADE)
        scene = state.get("scene")
        if not self._invert:
            if scene == SCENE_OFF or scene == SCENE_COVER_CLOSE:
                return True
            if scene == SCENE_COVER_OPEN:
                return False
        else:
            # Inverted: open scene means closed in HA
            if scene == SCENE_COVER_OPEN:
                return True
            if scene == SCENE_OFF or scene == SCENE_COVER_CLOSE:
                return False
        value = state.get("value")
        if value is not None:
            ha_pos = self._ds_to_ha_position(value)
            return ha_pos == 0
        return None

    async def async_open_cover(self, **kwargs: Any) -> None:
        scene = SCENE_COVER_CLOSE if self._invert else SCENE_COVER_OPEN
        ds_value = 0 if self._invert else 255
        await self.coordinator.api.call_scene(
            self._zone_id, GROUP_SHADE, scene
        )
        self.coordinator.set_zone_state(
            self._zone_id, GROUP_SHADE, scene=scene, value=ds_value
        )
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        scene = SCENE_COVER_OPEN if self._invert else SCENE_COVER_CLOSE
        ds_value = 255 if self._invert else 0
        await self.coordinator.api.call_scene(
            self._zone_id, GROUP_SHADE, scene
        )
        self.coordinator.set_zone_state(
            self._zone_id, GROUP_SHADE, scene=scene, value=ds_value
        )
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self.coordinator.api.call_scene(
            self._zone_id, GROUP_SHADE, SCENE_COVER_STOP
        )
        self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs.get(ATTR_POSITION, 0)
        ds_value = self._ha_to_ds_value(position)
        await self.coordinator.api.set_value(
            self._zone_id, GROUP_SHADE, ds_value
        )
        self.coordinator.set_zone_state(
            self._zone_id, GROUP_SHADE, value=ds_value
        )
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
