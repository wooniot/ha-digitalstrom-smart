"""Climate entities for Digital Strom zones.

Full thermostat control: set target temperature, switch heating/cooling modes.
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
    GROUP_COOLING,
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

# HA preset -> dS temperature-control operation-mode scene (GROUP_TEMP_CONTROL = 48).
# Fix #32: was wrongly mapped to generic output scenes 5/17/18/19 on GROUP_HEATING (3),
# which the temperature controller ignores (silent no-op). The controller listens on
# group 48 with the operation-mode index as the scene number.
PRESET_TO_SCENE = {
    "off": 0,
    "comfort": 1,
    "economy": 2,
    "night": 4,
    "holiday": 5,
}

# dS operation-mode number -> setTemperatureControlValues parameter name (fix #32).
OP_MODE_PARAM = {0: "Off", 1: "Comfort", 2: "Economy", 4: "Night", 5: "Holiday"}

# dS ControlMode values
CONTROL_MODE_OFF = 0
CONTROL_MODE_PID = 1       # Heating
CONTROL_MODE_ZONE_FOLLOWER = 2
CONTROL_MODE_FIXED = 3
CONTROL_MODE_MANUAL = 4
CONTROL_MODE_COOLING = 11  # Cooling
CONTROL_MODE_COOL_OFF = 12


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
        # Zone needs temp control data (not just dumb heating actuators)
        if coordinator.has_temp_control(zone_id):
            entities.append(
                DigitalStromClimate(coordinator, zone_id, zone_info)
            )

    async_add_entities(entities)


class DigitalStromClimate(CoordinatorEntity, ClimateEntity):
    """A Digital Strom zone thermostat with heating and cooling support."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF, HVACMode.AUTO]
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
        self._attr_translation_key = "zone_climate"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": self._zone_name,
            "manufacturer": MANUFACTURER,
            "model": "Zone",
        }

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
            nv = status.get("NominalValue")
            if nv and nv > 0:
                return nv
        return self.coordinator.get_temperature(self._zone_id)

    def _safe_int(self, value, default: int = 0) -> int:
        """Convert value to int safely (dSS may return strings)."""
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return default
        return default

    def _is_cooling_mode(self, status: dict) -> bool:
        """Detect if zone is in cooling mode.

        Primary: heating_system_mode stateChange event (most reliable).
        When dSS switches to cooling, the heating controller goes off and
        getTemperatureControlStatus only returns {ControlMode: 0, ControlState: 0}
        with NO cooling indicator. The real signal is the apartment-level
        heating_system_mode event: active=heating, inactive=cooling.
        """
        # Primary: coordinator tracks heating_system_mode event
        if self.coordinator.is_cooling_mode:
            return True

        # Fallback: check status fields for "cool" keyword
        for key in ("ControlMode", "ControlState", "State", "state", "mode"):
            val = str(status.get(key, "")).lower()
            if "cool" in val:
                return True

        # Fallback: numeric ControlMode (11=cooling, 12=cool_off)
        control_mode = self._safe_int(status.get("ControlMode"), -1)
        if control_mode in (CONTROL_MODE_COOLING, CONTROL_MODE_COOL_OFF):
            return True

        return False

    @property
    def hvac_mode(self) -> HVACMode:
        status = self.coordinator.get_climate_status(self._zone_id)
        if not status:
            return HVACMode.HEAT
        # Log status changes (not every poll) for diagnostics
        status_key = str(status.get("OperationMode", "")) + str(status.get("ControlMode", ""))
        if not hasattr(self, "_last_status_key") or self._last_status_key != status_key:
            self._last_status_key = status_key
            _LOGGER.info(
                "Zone %d (%s) climate status: %s",
                self._zone_id, self._zone_name, status,
            )
        # Check cooling FIRST — when dSS switches to cooling, the heating
        # OperationMode becomes 0 (off), but cooling is active
        if self._is_cooling_mode(status):
            return HVACMode.COOL
        op_mode = self._safe_int(status.get("OperationMode"), 0)
        if op_mode == 0:
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        status = self.coordinator.get_climate_status(self._zone_id)
        if not status:
            return None
        if self._is_cooling_mode(status):
            control_value = status.get("ControlValue", 0)
            if isinstance(control_value, str):
                try:
                    control_value = float(control_value)
                except ValueError:
                    control_value = 0
            return HVACAction.COOLING if control_value > 0 else HVACAction.IDLE
        op_mode = self._safe_int(status.get("OperationMode"), 0)
        if op_mode == 0:
            return HVACAction.OFF
        control_value = status.get("ControlValue", 0)
        if isinstance(control_value, str):
            try:
                control_value = float(control_value)
            except ValueError:
                control_value = 0
        if control_value > 0:
            if self._is_cooling_mode(status):
                return HVACAction.COOLING
            return HVACAction.HEATING
        return HVACAction.IDLE

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
        # Fix #32: write the setpoint of the ACTIVE operation mode via its per-mode
        # parameter (e.g. Comfort=21); NominalValue is read-only and was ignored.
        status = self.coordinator.get_climate_status(self._zone_id)
        op_mode = (status or {}).get("OperationMode", 1)
        mode_param = OP_MODE_PARAM.get(op_mode, "Comfort")
        try:
            await self.coordinator.api.set_temperature_control_values(
                self._zone_id, temp, mode_param
            )
            # Update local state
            if status:
                status["NominalValue"] = temp
            self.async_write_ha_state()
        except DigitalStromApiError as err:
            _LOGGER.error("Failed to set temperature for %s: %s", self._zone_name, err)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode (heat/cool/off/auto)."""
        # Fix #32: operation-mode scenes live on GROUP_TEMP_CONTROL (48), not GROUP_HEATING (3).
        if hvac_mode == HVACMode.OFF:
            scene = 0        # Off/Protection
        else:
            scene = 1        # Comfort
        try:
            await self.coordinator.api.call_scene(
                self._zone_id, GROUP_TEMP_CONTROL, scene
            )
            self.async_write_ha_state()
        except DigitalStromApiError as err:
            _LOGGER.error("Failed to set HVAC mode for %s: %s", self._zone_name, err)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set heating preset (comfort/economy/night/holiday)."""
        scene = PRESET_TO_SCENE.get(preset_mode, 1)  # default Comfort
        try:
            # Fix #32: switch operation mode on GROUP_TEMP_CONTROL (48), not GROUP_HEATING (3).
            await self.coordinator.api.call_scene(
                self._zone_id, GROUP_TEMP_CONTROL, scene
            )
            self.async_write_ha_state()
        except DigitalStromApiError as err:
            _LOGGER.error("Failed to set preset for %s: %s", self._zone_name, err)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
