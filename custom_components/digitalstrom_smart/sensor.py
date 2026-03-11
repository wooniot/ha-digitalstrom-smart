"""Sensor entities for Digital Strom.

Free: apartment power consumption, zone temperature
Pro: outdoor weather sensors, per-circuit power, humidity, brightness, CO2
"""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfTemperature, PERCENTAGE

# Import units that may have moved between HA versions
try:
    from homeassistant.const import UnitOfIlluminance
except ImportError:
    class UnitOfIlluminance:
        LUX = "lx"

try:
    from homeassistant.const import UnitOfSpeed
except ImportError:
    class UnitOfSpeed:
        METERS_PER_SECOND = "m/s"

try:
    from homeassistant.const import UnitOfPressure
except ImportError:
    class UnitOfPressure:
        HPA = "hPa"

try:
    from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION
except ImportError:
    CONCENTRATION_PARTS_PER_MILLION = "ppm"
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, CONF_ENABLED_ZONES, GROUP_TEMP_CONTROL
from .coordinator import DigitalStromCoordinator

_LOGGER = logging.getLogger(__name__)

# Outdoor sensor definitions (PRO)
OUTDOOR_SENSORS = {
    "temperature": {
        "name": "Outdoor Temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
    },
    "humidity": {
        "name": "Outdoor Humidity",
        "device_class": SensorDeviceClass.HUMIDITY,
        "unit": PERCENTAGE,
    },
    "brightness": {
        "name": "Outdoor Brightness",
        "device_class": SensorDeviceClass.ILLUMINANCE,
        "unit": UnitOfIlluminance.LUX,
    },
    "windspeed": {
        "name": "Wind Speed",
        "device_class": SensorDeviceClass.WIND_SPEED,
        "unit": UnitOfSpeed.METERS_PER_SECOND,
    },
    "windgust": {
        "name": "Wind Gust",
        "device_class": SensorDeviceClass.WIND_SPEED,
        "unit": UnitOfSpeed.METERS_PER_SECOND,
    },
    "airpressure": {
        "name": "Air Pressure",
        "device_class": SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        "unit": UnitOfPressure.HPA,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Digital Strom sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DigitalStromCoordinator = data["coordinator"]
    enabled_zones = entry.data.get(CONF_ENABLED_ZONES, [])

    entities: list[SensorEntity] = []

    # --- FREE: Apartment energy sensor ---
    entities.append(DigitalStromEnergySensor(coordinator))

    # --- FREE: Temperature sensors per zone ---
    for zone_id, zone_info in coordinator.zones.items():
        if enabled_zones and zone_id not in enabled_zones:
            continue

        if coordinator.has_temp_control(zone_id):
            # Zone with temperature control (group 48): current + target temp
            if coordinator.get_current_temperature(zone_id) is not None:
                entities.append(
                    DigitalStromCurrentTempSensor(coordinator, zone_id, zone_info)
                )
            if coordinator.get_temperature(zone_id) is not None:
                entities.append(
                    DigitalStromTargetTempSensor(coordinator, zone_id, zone_info)
                )
            # Heating control output (0-100%)
            if coordinator.get_control_value(zone_id) is not None:
                entities.append(
                    DigitalStromHeatingOutputSensor(coordinator, zone_id, zone_info)
                )
        elif coordinator.get_temperature(zone_id) is not None:
            # Zone without temp control: single temperature sensor (legacy)
            entities.append(
                DigitalStromTemperatureSensor(coordinator, zone_id, zone_info)
            )

    # --- PRO: Outdoor weather sensors ---
    if coordinator.pro_enabled and coordinator.outdoor_sensors:
        for sensor_key, sensor_def in OUTDOOR_SENSORS.items():
            if sensor_key in coordinator.outdoor_sensors:
                entities.append(
                    DigitalStromOutdoorSensor(
                        coordinator, sensor_key, sensor_def
                    )
                )

    # --- PRO: Per-circuit power sensors ---
    if coordinator.pro_enabled and coordinator.circuits:
        for circuit in coordinator.circuits:
            dsuid = circuit.get("dSUID", "")
            if dsuid:
                entities.append(
                    DigitalStromCircuitSensor(coordinator, circuit)
                )

    async_add_entities(entities)


class DigitalStromEnergySensor(CoordinatorEntity, SensorEntity):
    """Apartment-level power consumption sensor."""

    _attr_has_entity_name = True
    _attr_name = "Power Consumption"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, coordinator: DigitalStromCoordinator) -> None:
        super().__init__(coordinator)
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_apartment_consumption"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Server",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    @property
    def available(self) -> bool:
        return not self.coordinator.is_paused and super().available

    @property
    def native_value(self) -> int | None:
        return self.coordinator.consumption

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromTemperatureSensor(CoordinatorEntity, SensorEntity):
    """Zone temperature sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        zone_id: int,
        zone_info: dict,
    ) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_{zone_id}_temperature"
        self._attr_name = "Temperature"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": zone_info["name"],
            "manufacturer": MANUFACTURER,
            "model": "Zone",
        }

    @property
    def available(self) -> bool:
        return not self.coordinator.is_paused and super().available

    @property
    def native_value(self) -> float | None:
        return self.coordinator.get_temperature(self._zone_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromCurrentTempSensor(CoordinatorEntity, SensorEntity):
    """Current (measured) temperature in a zone with temperature control."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, zone_id, zone_info):
        super().__init__(coordinator)
        self._zone_id = zone_id
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_{zone_id}_current_temp"
        self._attr_name = "Temperature"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": zone_info["name"],
            "manufacturer": MANUFACTURER,
            "model": "Zone",
        }

    @property
    def available(self):
        return not self.coordinator.is_paused and super().available

    @property
    def native_value(self):
        return self.coordinator.get_current_temperature(self._zone_id)

    @callback
    def _handle_coordinator_update(self):
        self.async_write_ha_state()


class DigitalStromTargetTempSensor(CoordinatorEntity, SensorEntity):
    """Target (nominal) temperature in a zone with temperature control."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, zone_id, zone_info):
        super().__init__(coordinator)
        self._zone_id = zone_id
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_{zone_id}_target_temp"
        self._attr_name = "Target Temperature"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": zone_info["name"],
            "manufacturer": MANUFACTURER,
            "model": "Zone",
        }

    @property
    def available(self):
        return not self.coordinator.is_paused and super().available

    @property
    def native_value(self):
        return self.coordinator.get_temperature(self._zone_id)

    @callback
    def _handle_coordinator_update(self):
        self.async_write_ha_state()


class DigitalStromHeatingOutputSensor(CoordinatorEntity, SensorEntity):
    """Heating control output (0-100%) for a zone with temperature control."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator, zone_id, zone_info):
        super().__init__(coordinator)
        self._zone_id = zone_id
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_{zone_id}_heating_output"
        self._attr_name = "Heating Output"
        self._attr_icon = "mdi:radiator"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": zone_info["name"],
            "manufacturer": MANUFACTURER,
            "model": "Zone",
        }

    @property
    def available(self):
        return not self.coordinator.is_paused and super().available

    @property
    def native_value(self):
        val = self.coordinator.get_control_value(self._zone_id)
        if val is not None:
            return round(val * 100 / 255) if val > 1 else round(val * 100)
        return None

    @callback
    def _handle_coordinator_update(self):
        self.async_write_ha_state()


class DigitalStromOutdoorSensor(CoordinatorEntity, SensorEntity):
    """Outdoor weather sensor from dSS. PRO."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        sensor_key: str,
        sensor_def: dict,
    ) -> None:
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_outdoor_{sensor_key}"
        self._attr_name = sensor_def["name"]
        self._attr_device_class = sensor_def["device_class"]
        self._attr_native_unit_of_measurement = sensor_def["unit"]
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Server",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    @property
    def available(self) -> bool:
        return not self.coordinator.is_paused and super().available

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.outdoor_sensors.get(self._sensor_key, {})
        return data.get("value")

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromCircuitSensor(CoordinatorEntity, SensorEntity):
    """Per-circuit (dSM) power consumption sensor. PRO."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        circuit: dict,
    ) -> None:
        super().__init__(coordinator)
        self._dsuid = circuit.get("dSUID", "")
        dss_id = coordinator.dss_id
        circuit_name = circuit.get("name", self._dsuid[:8])
        self._attr_unique_id = f"ds_{dss_id}_circuit_{self._dsuid}"
        self._attr_name = f"Circuit {circuit_name}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Server",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    @property
    def available(self) -> bool:
        return not self.coordinator.is_paused and super().available

    @property
    def native_value(self) -> int | None:
        return self.coordinator.get_circuit_power(self._dsuid) or None

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
