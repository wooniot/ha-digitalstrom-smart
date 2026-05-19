"""Sensor entities for Digital Strom.

Free: apartment power, per-circuit (dSM) power, zone temperature, device sensors
Pro: outdoor weather sensors, humidity, brightness
"""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfEnergy, UnitOfTemperature, PERCENTAGE

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

from .const import (
    DOMAIN, MANUFACTURER, CONF_ENABLED_ZONES, GROUP_TEMP_CONTROL,
    SENSOR_TEMPERATURE, SENSOR_HUMIDITY, SENSOR_BRIGHTNESS, SENSOR_CO2,
    SENSOR_ACTIVE_POWER, SENSOR_ACTIVE_ENERGY,
    OUTDOOR_SENSOR_TRANSLATION_KEYS, DEVICE_SENSOR_TRANSLATION_KEYS,
)
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
    "rain": {
        "name": "Rain",
        "device_class": SensorDeviceClass.PRECIPITATION_INTENSITY,
        "unit": "mm/h",
    },
}

# Device sensor type to HA sensor config
DEVICE_SENSOR_MAP = {
    SENSOR_ACTIVE_POWER: {
        "suffix": "Power",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "icon": "mdi:lightning-bolt",
        "per_device": True,
    },
    SENSOR_ACTIVE_ENERGY: {
        "suffix": "Energy",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.WATT_HOUR,
        "icon": "mdi:lightning-bolt-circle",
        "per_device": True,
    },
    SENSOR_TEMPERATURE: {
        "suffix": "Temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
    },
    SENSOR_HUMIDITY: {
        "suffix": "Humidity",
        "device_class": SensorDeviceClass.HUMIDITY,
        "unit": PERCENTAGE,
    },
    SENSOR_BRIGHTNESS: {
        "suffix": "Brightness",
        "device_class": SensorDeviceClass.ILLUMINANCE,
        "unit": UnitOfIlluminance.LUX,
    },
    SENSOR_CO2: {
        "suffix": "CO2",
        "device_class": SensorDeviceClass.CO2,
        "unit": CONCENTRATION_PARTS_PER_MILLION,
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

    # --- FREE: License status (diagnostics) ---
    entities.append(DigitalStromLicenseSensor(coordinator))

    # --- FREE: Temperature sensors per zone ---
    for zone_id, zone_info in coordinator.zones.items():
        if enabled_zones and zone_id not in enabled_zones:
            continue

        if coordinator.has_temp_control(zone_id):
            # Zone with temperature control: current + target temp + heating output
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
        else:
            # Zone without temp control: show temperature if available from any source
            temp = coordinator.get_any_temperature(zone_id)
            if temp is not None:
                entities.append(
                    DigitalStromTemperatureSensor(coordinator, zone_id, zone_info)
                )

    # --- FREE: Device sensors (Ulux CO2, Lux, Temp, Humidity) ---
    for dsuid, dev in coordinator.devices.items():
        zone_id = dev.get("zone_id")
        if enabled_zones and zone_id not in enabled_zones:
            continue
        zone_name = dev.get("zone_name", "")
        dev_name = dev.get("name", "")
        for sensor in dev.get("sensors", []):
            stype = sensor.get("type", -1)
            if stype in DEVICE_SENSOR_MAP:
                sensor_config = DEVICE_SENSOR_MAP[stype]
                # Power/energy sensors always get an entity (value arrives via events)
                if sensor_config.get("per_device"):
                    has_value = True
                else:
                    has_value = (
                        sensor.get("value") is not None
                        or coordinator.get_device_sensor_value(dsuid, stype) is not None
                    )
                if has_value:
                    entities.append(
                        DigitalStromDeviceSensor(
                            coordinator, dsuid, dev, stype, sensor_config
                        )
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

    # --- FREE: Per-circuit (dSM) power + energy sensors ---
    if coordinator.circuits:
        for circuit in coordinator.circuits:
            dsuid = circuit.get("dSUID", "")
            if dsuid:
                entities.append(DigitalStromCircuitSensor(coordinator, circuit))
                entities.append(DigitalStromCircuitEnergySensor(coordinator, circuit))

    # --- FREE: Apartment-level energy (kWh) — sum of all dSMs ---
    if coordinator.circuits:
        entities.append(DigitalStromApartmentEnergySensor(coordinator))

    # --- FREE: User Defined States (text sensors; binary ones live in binary_sensor) ---
    for name, data in coordinator.user_states.items():
        if _is_binary_state(data):
            continue
        entities.append(DigitalStromUserStateSensor(coordinator, name))

    # Configurator timers/klokken are exposed as switch entities only
    # (one entity per timer to avoid duplicated sensor+switch pairs).

    async_add_entities(entities)


def _is_binary_state(data: dict) -> bool:
    """Return True if a dSS state behaves as binary (active/inactive)."""
    state = str(data.get("state", "")).lower()
    if state in ("active", "inactive"):
        return True
    value = data.get("value")
    if isinstance(value, (int, float)) and value in (1, 2):
        return True
    return False


class DigitalStromEnergySensor(CoordinatorEntity, SensorEntity):
    """Apartment-level power consumption sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "power_consumption"
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
    def native_value(self) -> int | None:
        return self.coordinator.consumption

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromLicenseSensor(CoordinatorEntity, SensorEntity):
    """License status diagnostics sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "license_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:license"

    def __init__(self, coordinator: DigitalStromCoordinator) -> None:
        super().__init__(coordinator)
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_license_status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Server",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    @property
    def native_value(self) -> str:
        info = self.coordinator.license_info
        if info.get("valid"):
            ltype = info.get("type", "pro")
            return f"Pro ({ltype})"
        return "Free"

    @property
    def extra_state_attributes(self) -> dict:
        info = self.coordinator.license_info
        attrs = {
            "valid": info.get("valid", False),
            "reason": info.get("reason", "unknown"),
            "license_type": info.get("type"),
            "validation_method": info.get("method"),
            "dss_id_sent": info.get("dss_id_sent", ""),
        }
        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromTemperatureSensor(CoordinatorEntity, SensorEntity):
    """Zone temperature sensor (rooms without temp control)."""

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
        self._attr_translation_key = "temperature"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": zone_info["name"],
            "manufacturer": MANUFACTURER,
            "model": "Zone",
            "suggested_area": zone_info["name"],
        }

    @property
    def native_value(self) -> float | None:
        return self.coordinator.get_any_temperature(self._zone_id)

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
        self._attr_translation_key = "current_temperature"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": zone_info["name"],
            "manufacturer": MANUFACTURER,
            "model": "Zone",
            "suggested_area": zone_info["name"],
        }

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
        self._attr_translation_key = "target_temperature"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": zone_info["name"],
            "manufacturer": MANUFACTURER,
            "model": "Zone",
            "suggested_area": zone_info["name"],
        }

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
        self._attr_translation_key = "heating_output"
        self._attr_icon = "mdi:radiator"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
            "name": zone_info["name"],
            "manufacturer": MANUFACTURER,
            "model": "Zone",
            "suggested_area": zone_info["name"],
        }

    @property
    def native_value(self):
        val = self.coordinator.get_control_value(self._zone_id)
        if val is not None:
            return round(val * 100 / 255) if val > 1 else round(val * 100)
        return None

    @callback
    def _handle_coordinator_update(self):
        self.async_write_ha_state()


class DigitalStromDeviceSensor(CoordinatorEntity, SensorEntity):
    """Device-level sensor (power/energy for Joker devices, CO2/temp/humidity for Ulux)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        dsuid: str,
        dev_info: dict,
        sensor_type: int,
        sensor_config: dict,
    ) -> None:
        super().__init__(coordinator)
        self._dsuid = dsuid
        self._sensor_type = sensor_type
        dss_id = coordinator.dss_id
        zone_id = dev_info.get("zone_id", 0)
        zone_name = dev_info.get("zone_name", "")
        dev_name = dev_info.get("name", "") or dsuid[:8]
        suffix = sensor_config["suffix"]
        self._attr_unique_id = f"ds_{dss_id}_dev_{dsuid}_{suffix.lower()}"
        translation_key = DEVICE_SENSOR_TRANSLATION_KEYS.get(sensor_type)
        if translation_key:
            self._attr_translation_key = translation_key
        else:
            self._attr_name = f"{dev_name} {suffix}"
        self._attr_device_class = sensor_config["device_class"]
        self._attr_native_unit_of_measurement = sensor_config["unit"]
        self._attr_state_class = sensor_config.get("state_class", SensorStateClass.MEASUREMENT)
        if "icon" in sensor_config:
            self._attr_icon = sensor_config["icon"]
        if sensor_config.get("per_device"):
            # Power/energy: own device entry, linked to the zone
            self._attr_device_info = {
                "identifiers": {(DOMAIN, f"{dss_id}_dev_{dsuid}")},
                "name": dev_name,
                "manufacturer": MANUFACTURER,
                "model": "Digital Strom Device",
                "via_device": (DOMAIN, f"{dss_id}_zone_{zone_id}"),
                "suggested_area": zone_name,
            }
        else:
            self._attr_device_info = {
                "identifiers": {(DOMAIN, f"{dss_id}_zone_{zone_id}")},
                "name": zone_name,
                "manufacturer": MANUFACTURER,
                "model": "Zone",
                "suggested_area": zone_name,
            }

    @property
    def native_value(self) -> float | None:
        val = self.coordinator.get_device_sensor_value(self._dsuid, self._sensor_type)
        if val is not None:
            return round(val, 1)
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
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
        translation_key = OUTDOOR_SENSOR_TRANSLATION_KEYS.get(sensor_key)
        if translation_key:
            self._attr_translation_key = translation_key
        else:
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
    def native_value(self) -> float | None:
        data = self.coordinator.outdoor_sensors.get(self._sensor_key, {})
        return data.get("value")

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromCircuitSensor(CoordinatorEntity, SensorEntity):
    """Per-circuit (dSM) instantaneous power consumption."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        circuit: dict,
    ) -> None:
        super().__init__(coordinator)
        self._dsuid = circuit.get("dSUID", "")
        dss_id = coordinator.dss_id
        circuit_name = circuit.get("name", self._dsuid[:8])
        hw_name = circuit.get("hwName", "dSM")
        self._attr_unique_id = f"ds_{dss_id}_circuit_{self._dsuid}"
        self._attr_translation_key = "circuit_power"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_circuit_{self._dsuid}")},
            "name": circuit_name,
            "manufacturer": MANUFACTURER,
            "model": hw_name,
            "via_device": (DOMAIN, f"{dss_id}_apartment"),
        }

    @property
    def native_value(self) -> int | None:
        val = self.coordinator.get_circuit_power(self._dsuid)
        return val if val else 0

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromCircuitEnergySensor(CoordinatorEntity, SensorEntity):
    """Per-circuit (dSM) cumulative energy meter — feeds HA Energy Dashboard."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        circuit: dict,
    ) -> None:
        super().__init__(coordinator)
        self._dsuid = circuit.get("dSUID", "")
        dss_id = coordinator.dss_id
        circuit_name = circuit.get("name", self._dsuid[:8])
        hw_name = circuit.get("hwName", "dSM")
        self._attr_unique_id = f"ds_{dss_id}_circuit_{self._dsuid}_energy"
        self._attr_translation_key = "circuit_energy"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_circuit_{self._dsuid}")},
            "name": circuit_name,
            "manufacturer": MANUFACTURER,
            "model": hw_name,
            "via_device": (DOMAIN, f"{dss_id}_apartment"),
        }

    @property
    def native_value(self) -> float | None:
        return self.coordinator.get_circuit_energy_kwh(self._dsuid)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromApartmentEnergySensor(CoordinatorEntity, SensorEntity):
    """Apartment-wide cumulative energy — sum of all dSM meters."""

    _attr_has_entity_name = True
    _attr_translation_key = "apartment_energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: DigitalStromCoordinator) -> None:
        super().__init__(coordinator)
        dss_id = coordinator.dss_id
        self._attr_unique_id = f"ds_{dss_id}_apartment_energy"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_apartment")},
            "name": "Digital Strom Server",
            "manufacturer": MANUFACTURER,
            "model": "dSS",
        }

    @property
    def native_value(self) -> float | None:
        return self.coordinator.apartment_energy_kwh

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DigitalStromUserStateSensor(CoordinatorEntity, SensorEntity):
    """A multi-valued dSS User Defined / apartment state (text sensor)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:state-machine"

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        state_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._state_name = state_name
        dss_id = coordinator.dss_id
        # Sanitize state name for unique_id (stable across renames in dSS)
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
    def native_value(self) -> str | None:
        data = self.coordinator.get_user_state(self._state_name)
        if not data:
            return None
        state = data.get("state")
        if state:
            return str(state)
        value = data.get("value")
        return str(value) if value is not None else None

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
