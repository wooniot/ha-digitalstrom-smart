"""Zone-based light entities for Digital Strom."""

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    GROUP_LIGHT,
    SCENE_OFF,
    SCENE_MAX,
    CONF_ENABLED_ZONES,
)
from .coordinator import DigitalStromCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Digital Strom lights."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DigitalStromCoordinator = data["coordinator"]
    enabled_zones = entry.data.get(CONF_ENABLED_ZONES, [])

    entities = []
    for zone_id, zone_info in coordinator.zones.items():
        if enabled_zones and zone_id not in enabled_zones:
            continue
        if GROUP_LIGHT in zone_info["groups"]:
            entities.append(DigitalStromLight(coordinator, zone_id, zone_info))

    async_add_entities(entities)


class DigitalStromLight(CoordinatorEntity, LightEntity):
    """A Digital Strom zone light (controls all lights in zone via scenes)."""

    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        zone_id: int,
        zone_info: dict,
    ) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._zone_name = zone_info["name"]
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_{zone_id}_light"
        self._attr_translation_key = "zone_light"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": self._zone_name,
            "manufacturer": MANUFACTURER,
            "model": "Zone",
        }

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.get_zone_state(self._zone_id, GROUP_LIGHT)
        return state.get("is_on")

    @property
    def brightness(self) -> int | None:
        state = self.coordinator.get_zone_state(self._zone_id, GROUP_LIGHT)
        value = state.get("value")
        if value is not None:
            return value  # Already 0-255
        # Infer from scene
        if state.get("is_on") is True:
            return 255
        if state.get("is_on") is False:
            return 0
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is not None:
            await self.coordinator.api.set_value(
                self._zone_id, GROUP_LIGHT, brightness
            )
            self.coordinator.set_zone_state(
                self._zone_id, GROUP_LIGHT, is_on=brightness > 0, value=brightness
            )
        else:
            await self.coordinator.api.call_scene(
                self._zone_id, GROUP_LIGHT, SCENE_MAX
            )
            self.coordinator.set_zone_state(
                self._zone_id, GROUP_LIGHT, is_on=True, value=255
            )
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.api.call_scene(
            self._zone_id, GROUP_LIGHT, SCENE_OFF
        )
        self.coordinator.set_zone_state(
            self._zone_id, GROUP_LIGHT, is_on=False, value=0
        )
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
