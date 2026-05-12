"""Binary sensor entities for Digital Strom.

Free: Joker sensor devices (contacts, smoke detectors, door sensors)
Pro: Rain detection from outdoor weather station
"""

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, GROUP_JOKER, CONF_ENABLED_ZONES, APARTMENT_WEATHER_SCENES, WEATHER_TRANSLATION_KEYS, SCENE_RAIN
from .coordinator import DigitalStromCoordinator

_LOGGER = logging.getLogger(__name__)

# Map dSS binaryInput inputType to HA device class
# See dSS documentation for inputType values
BINARY_INPUT_DEVICE_CLASS = {
    1: BinarySensorDeviceClass.PRESENCE,      # Presence
    2: BinarySensorDeviceClass.LIGHT,         # Brightness
    3: BinarySensorDeviceClass.PRESENCE,      # Presence in darkness
    4: BinarySensorDeviceClass.VIBRATION,     # Twilight
    5: BinarySensorDeviceClass.MOTION,        # Motion
    6: BinarySensorDeviceClass.MOTION,        # Motion in darkness
    7: BinarySensorDeviceClass.SMOKE,         # Smoke
    8: BinarySensorDeviceClass.WINDOW,        # Wind strength above limit
    9: BinarySensorDeviceClass.MOISTURE,      # Rain
    10: BinarySensorDeviceClass.HEAT,         # Solar radiation
    11: BinarySensorDeviceClass.PROBLEM,      # Temperature below limit
    12: BinarySensorDeviceClass.BATTERY,      # Battery status
    13: BinarySensorDeviceClass.WINDOW,       # Window contact
    14: BinarySensorDeviceClass.DOOR,         # Door contact
    15: BinarySensorDeviceClass.WINDOW,       # Window handle
    16: BinarySensorDeviceClass.OPENING,      # Generic input (UMR contacts, etc.)
    18: BinarySensorDeviceClass.TAMPER,       # Malfunction / tamper
    19: BinarySensorDeviceClass.SAFETY,       # Safety
}

# Default device class if inputType is unknown
DEFAULT_BINARY_CLASS = BinarySensorDeviceClass.OPENING

# Input types where dSS "active" (state=1) means contact CLOSED (door/window shut).
# For these types, HA is_on must be inverted: is_on=True means OPEN (no contact).
# Non-contact types (motion, presence, smoke) are NOT inverted.
CONTACT_INPUT_TYPES = {
    0,   # Generic / default (UMR contacts, generic inputs)
    13,  # Window contact
    14,  # Door contact
    15,  # Window handle
    16,  # Generic input (UMR contacts, etc.)
    21,  # Room temperature/humidity sensor active (Raumfühler)
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Digital Strom binary sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DigitalStromCoordinator = data["coordinator"]
    enabled_zones = entry.data.get(CONF_ENABLED_ZONES, [])

    entities = []

    # --- FREE: Joker sensor devices (contacts, smoke, door) ---
    for zone_id, zone_info in coordinator.zones.items():
        if enabled_zones and zone_id not in enabled_zones:
            continue
        if GROUP_JOKER not in zone_info["groups"]:
            continue

        for dev in coordinator.get_joker_sensors_in_zone(zone_id):
            _LOGGER.info(
                "Binary sensor (pure sensor): %s (%s) zone=%s inputType=%s",
                dev["dsuid"][:8], dev.get("name", ""),
                zone_info["name"],
                dev.get("binary_inputs", [{}])[0].get("inputType", "?") if dev.get("binary_inputs") else "none",
            )
            entities.append(
                DigitalStromJokerBinarySensor(coordinator, zone_id, zone_info, dev)
            )

        # Also detect Joker devices with binaryInputs that have outputMode > 0
        # (e.g. EnOcean window contacts, SW-UMR200 configured as actuator+sensor)
        for dev in coordinator.get_joker_binary_input_devices_in_zone(zone_id):
            _LOGGER.info(
                "Binary sensor (actuator+sensor): %s (%s) zone=%s outputMode=%s inputType=%s",
                dev["dsuid"][:8], dev.get("name", ""),
                zone_info["name"], dev.get("output_mode", 0),
                dev.get("binary_inputs", [{}])[0].get("inputType", "?") if dev.get("binary_inputs") else "none",
            )
            entities.append(
                DigitalStromJokerBinarySensor(coordinator, zone_id, zone_info, dev)
            )

    # --- PRO: Rain detection from outdoor weather data ---
    if coordinator.pro_enabled and coordinator.outdoor_sensors and "rain" in coordinator.outdoor_sensors:
        entities.append(DigitalStromRainSensor(coordinator))

    # --- PRO: Weather protection binary sensors (Wind, Rain scenes) ---
    if coordinator.pro_enabled:
        for scene_nr, name in APARTMENT_WEATHER_SCENES.items():
            entities.append(
                DigitalStromWeatherProtectionSensor(coordinator, scene_nr, name)
            )

    # --- FREE: User Defined States that behave as binary (active/inactive) ---
    for name, data in coordinator.user_states.items():
        if _is_binary_state(data):
            entities.append(DigitalStromUserBinaryState(coordinator, name))

    # --- FREE: Configurator User Defined States (custom-states with proper names) ---
    for sid, data in coordinator.custom_states.items():
        entities.append(DigitalStromCustomState(coordinator, sid, data))

    async_add_entities(entities)


def _is_binary_state(data: dict) -> bool:
    """Mirror of sensor._is_binary_state — keep them in sync."""
    state = str(data.get("state", "")).lower()
    if state in ("active", "inactive"):
        return True
    value = data.get("value")
    if isinstance(value, (int, float)) and value in (1, 2):
        return True
    return False


class DigitalStromJokerBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """A Digital Strom Joker sensor device (contact, smoke detector, etc.)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        zone_id: int,
        zone_info: dict,
        device: dict,
    ) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._zone_name = zone_info["name"]
        self._dsuid = device["dsuid"]
        self._device_name = device.get("name", "")
        dss_id = coordinator.dss_id

        self._attr_unique_id = f"ds_{dss_id}_{self._dsuid}_joker_binary"

        # Use device name from dS if available
        if self._device_name:
            self._attr_name = self._device_name
        else:
            self._attr_name = "Sensor"

        # Determine device class from binaryInputs
        binary_inputs = device.get("binary_inputs", [])
        self._input_type = 0
        if binary_inputs:
            self._input_type = binary_inputs[0].get("inputType", 0)
            self._attr_device_class = BINARY_INPUT_DEVICE_CLASS.get(
                self._input_type, DEFAULT_BINARY_CLASS
            )
        else:
            self._attr_device_class = DEFAULT_BINARY_CLASS

        # Contact-type sensors need inverted logic:
        # dSS: state 1 = active = contact closed (door/window shut)
        # HA:  is_on = True = detected = door/window OPEN
        # So for contacts: invert. For motion/presence: don't invert.
        self._invert = self._input_type in CONTACT_INPUT_TYPES

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": self._zone_name,
            "manufacturer": MANUFACTURER,
            "model": "Zone",
        }

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.get_device_on_state(self._dsuid)
        if state is None:
            return None
        return not state if self._invert else state

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromWeatherProtectionSensor(CoordinatorEntity, BinarySensorEntity):
    """Weather protection binary sensor (Wind/Rain scenes). PRO.

    These are triggered automatically by the dSS when weather thresholds
    are exceeded. Read-only — not controllable by the user.
    """

    _attr_has_entity_name = True

    _ICONS = {
        "Rain": "mdi:weather-rainy",
    }

    def __init__(
        self, coordinator: DigitalStromCoordinator, scene_nr: int, name: str,
    ) -> None:
        super().__init__(coordinator)
        self._scene_nr = scene_nr
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_weather_{scene_nr}"
        tkey = WEATHER_TRANSLATION_KEYS.get(scene_nr)
        if tkey:
            self._attr_translation_key = tkey
        else:
            self._attr_name = f"{name} Protection"
        self._attr_icon = self._ICONS.get(name, "mdi:alert")
        self._attr_device_class = BinarySensorDeviceClass.MOISTURE if scene_nr == SCENE_RAIN else BinarySensorDeviceClass.SAFETY
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Server",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_alarm_active(self._scene_nr)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromUserBinaryState(CoordinatorEntity, BinarySensorEntity):
    """A binary dSS User Defined / apartment state (active=on, inactive=off)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:toggle-switch-outline"

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        state_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._state_name = state_name
        dss_id = coordinator.dss_id
        safe = state_name.replace(".", "_").replace(" ", "_")
        self._attr_unique_id = f"ds_{dss_id}_userstate_{safe}"
        self._attr_name = coordinator.friendly_state_name(state_name)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Server",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.get_user_state(self._state_name)
        if not data:
            return None
        state = str(data.get("state", "")).lower()
        if state == "active":
            return True
        if state == "inactive":
            return False
        value = data.get("value")
        if value == 1:
            return True
        if value == 2:
            return False
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromCustomState(CoordinatorEntity, BinarySensorEntity):
    """A User Defined State created in the dSS Configurator.

    Display name comes from the Configurator (e.g. "Schoonmaak"). The
    runtime value follows the addon-state with active=on, inactive=off.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:state-machine"

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        state_id: str,
        data: dict,
    ) -> None:
        super().__init__(coordinator)
        self._state_id = state_id
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_customstate_{state_id}"
        self._attr_name = data.get("name", f"State {state_id}")
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Server",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.get_custom_state(self._state_id)
        if not data:
            return None
        state = str(data.get("state", "")).lower()
        if state == "active":
            return True
        if state == "inactive":
            return False
        value = data.get("value")
        if value == 1:
            return True
        if value == 2:
            return False
        return None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.get_custom_state(self._state_id) or {}
        return {
            "set_name": data.get("set_name"),
            "reset_name": data.get("reset_name"),
            "state_id": self._state_id,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromRainSensor(CoordinatorEntity, BinarySensorEntity):
    """Rain detection binary sensor from dSS weather station. PRO."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_translation_key = "rain"

    def __init__(self, coordinator: DigitalStromCoordinator) -> None:
        super().__init__(coordinator)
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_outdoor_rain_binary"
        self._attr_icon = "mdi:weather-rainy"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Server",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if it is raining (rain value > 0)."""
        data = self.coordinator.outdoor_sensors.get("rain", {})
        value = data.get("value")
        if value is not None:
            return float(value) > 0
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
