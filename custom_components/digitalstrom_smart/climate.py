"""Climate entities for Digital Strom zones.

Full thermostat control: set target temperature, switch heating modes.
PRO FEATURE - requires license key.
"""

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DigitalStromApiError
from .const import (
    DOMAIN,
    MANUFACTURER,
    GROUP_HEATING,
    GROUP_TEMP_CONTROL,
    SCENE_OFF,
    SCENE_1,
    SCENE_2,
    SCENE_3,
    SCENE_4,
    CONF_ENABLED_ZONES,
)
from .coordinator import DigitalStromCoordinator

_LOGGER = logging.getLogger(__name__)

# dS OperationMode to HA preset
DS_PRESET_MAP = {
    0: "off",
    1: "comfort",
    2: "economy",
    4: "night",
    5: "holiday",
}

# HA preset to dS scene number (for GROUP_HEATING)
PRESET_TO_SCENE = {
    "off": SCENE_OFF,
    "comfort": SCENE_1,
    "economy": SCENE_2,
    "night": SCENE_3,
    "holiday": SCENE_4,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Digital Strom climate entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DigitalStromCoordinator = data["coordinator"]
    enabled_zones = entry.data.get(CONF_ENABLED_ZONES, [])

    entities = []
    for zone_id, zone_info in coordinator.zones.items():
        if enabled_zones and zone_id not in enabled_zones:
            continue
        # Zone needs heating or temperature control group
        has_heating = GROUP_HEATING in zone_info["groups"] or GROUP_TEMP_CONTROL in zone_info["groups"]
        if has_heating and coordinator.get_climate_status(zone_id):
            entities.append(
                DigitalStromClimate(coordinator, zone_id, zone_info)
            )

    async_add_entities(entities)


class DigitalStromClimate(CoordinatorEntity, ClimateEntity):
    """A Digital Strom zone thermostat."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = ["comfort", "economy", "night", "holiday"]
    _attr_min_temp = 5.0
    _attr_max_temp = 30.0
    _attr_target_temperature_step = 0.5
    _enable_turn_on_off_backwards_compat = False

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
        self._attr_unique_id = f"ds_{dss_id}_{zone_id}_climate"
        self._attr_name = "Climate"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": self._zone_name,
            "manufacturer": MANUFACTURER,
            "model": "Zone",
        }

    @property
    def available(self) -> bool:
        return not self.coordinator.is_paused and super().available

    @property
    def current_temperature(self) -> float | None:
        status = self.coordinator.get_climate_status(self._zone_id)
        if status:
            temp = status.get("TemperatureValue")
            if temp and temp > 0:
                return temp
        return self.coordinator.get_current_temperature(self._zone_id)

    @property
    def target_temperature(self) -> float | None:
        status = self.coordinator.get_climate_status(self._zone_id)
        if status:
            return status.get("NominalValue")
        return self.coordinator.get_temperature(self._zone_id)

    @property
    def hvac_mode(self) -> HVACMode:
        status = self.coordinator.get_climate_status(self._zone_id)
        if status:
            op_mode = status.get("OperationMode", 0)
            if op_mode == 0:
                return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        status = self.coordinator.get_climate_status(self._zone_id)
        if status:
            control_value = status.get("ControlValue", 0)
            if control_value > 0:
                return HVACAction.HEATING
            return HVACAction.IDLE
        return None

    @property
    def preset_mode(self) -> str | None:
        status = self.coordinator.get_climate_status(self._zone_id)
        if status:
            op_mode = status.get("OperationMode", 1)
            return DS_PRESET_MAP.get(op_mode, "comfort")
        return None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        try:
            await self.coordinator.api.set_temperature_control_values(
                self._zone_id, temp
            )
            # Update local state
            status = self.coordinator.get_climate_status(self._zone_id)
            if status:
                status["NominalValue"] = temp
            self.async_write_ha_state()
        except DigitalStromApiError as err:
            _LOGGER.error("Failed to set temperature for %s: %s", self._zone_name, err)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode (heat/off)."""
        if hvac_mode == HVACMode.OFF:
            scene = SCENE_OFF
        else:
            scene = SCENE_1  # Comfort
        try:
            await self.coordinator.api.call_scene(
                self._zone_id, GROUP_HEATING, scene
            )
            self.async_write_ha_state()
        except DigitalStromApiError as err:
            _LOGGER.error("Failed to set HVAC mode for %s: %s", self._zone_name, err)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set heating preset (comfort/economy/night/holiday)."""
        scene = PRESET_TO_SCENE.get(preset_mode, SCENE_1)
        try:
            await self.coordinator.api.call_scene(
                self._zone_id, GROUP_HEATING, scene
            )
            self.async_write_ha_state()
        except DigitalStromApiError as err:
            _LOGGER.error("Failed to set preset for %s: %s", self._zone_name, err)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
