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

from .const import DOMAIN, MANUFACTURER, GROUP_JOKER, CONF_ENABLED_ZONES
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
    16: BinarySensorDeviceClass.GAS,          # Gas detected
    18: BinarySensorDeviceClass.TAMPER,       # Malfunction / tamper
    19: BinarySensorDeviceClass.SAFETY,       # Safety
}

# Default device class if inputType is unknown
DEFAULT_BINARY_CLASS = BinarySensorDeviceClass.OPENING


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
            entities.append(
                DigitalStromJokerBinarySensor(coordinator, zone_id, zone_info, dev)
            )

    # --- PRO: Rain detection from outdoor weather data ---
    if coordinator.pro_enabled and coordinator.outdoor_sensors and "rain" in coordinator.outdoor_sensors:
        entities.append(DigitalStromRainSensor(coordinator))

    async_add_entities(entities)


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
        if binary_inputs:
            input_type = binary_inputs[0].get("inputType", 0)
            self._attr_device_class = BINARY_INPUT_DEVICE_CLASS.get(
                input_type, DEFAULT_BINARY_CLASS
            )
        else:
            self._attr_device_class = DEFAULT_BINARY_CLASS

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": self._zone_name,
            "manufacturer": MANUFACTURER,
            "model": "Zone",
        }

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.get_device_on_state(self._dsuid)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromRainSensor(CoordinatorEntity, BinarySensorEntity):
    """Rain detection binary sensor from dSS weather station. PRO."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_name = "Rain"

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
