"""Event listener and data coordinator for Digital Strom.

Central hub: manages event subscriptions, periodic polling,
scene discovery, sensor data, and state tracking.
"""

import asyncio
import logging
import time as _time
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DigitalStromApi, DigitalStromApiError, DigitalStromAuthError
import aiohttp

from .const import (
    DOMAIN,
    POLL_INTERVAL_ENERGY,
    RECONNECT_INITIAL,
    RECONNECT_MAX,
    GROUP_LIGHT,
    GROUP_SHADE,
    GROUP_HEATING,
    GROUP_JOKER,
    GROUP_COOLING,
    GROUP_TEMP_CONTROL,
    SCENE_OFF,
    SCENE_1,
    SCENE_2,
    SCENE_3,
    SCENE_4,
    NAMED_SCENES,
    NAMED_SCENES_SHADE,
    GROUP_HEATING_SCENES,
    SENSOR_TEMPERATURE,
    SENSOR_HUMIDITY,
    SENSOR_BRIGHTNESS,
    SENSOR_CO2,
    INTEGRATION_VERSION,
    TELEMETRY_URL,
    PRESENCE_SCENE_NUMBERS,
    ALARM_SCENE_NUMBERS,
    SCENE_PRESENT,
)

_LOGGER = logging.getLogger(__name__)

# Groups for which we create scene entities
SCENE_GROUPS = (GROUP_LIGHT, GROUP_SHADE, GROUP_HEATING)


class DigitalStromCoordinator(DataUpdateCoordinator):
    """Coordinator: manages event listener + periodic polling."""

    def __init__(
        self, hass: HomeAssistant, api: DigitalStromApi,
        structure: dict, dss_id: str = "",
    ) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(seconds=POLL_INTERVAL_ENERGY),
        )
        self.api = api
        self._structure = structure
        self.dss_id = dss_id
        self._event_task: asyncio.Task | None = None
        self._reconnect_delay = RECONNECT_INITIAL

        # State tracking: {(zone_id, group): {"scene": int, "value": int, "is_on": bool}}
        self._zone_states: dict[tuple[int, int], dict[str, Any]] = {}

        # Sensor data
        self._consumption: int = 0
        self._temperatures: dict[int, dict] = {}  # zone_id -> temp data
        self._outdoor_sensors: dict = {}  # outdoor weather data
        self._zone_sensors: dict[int, dict] = {}  # zone_id -> sensor readings

        # Device sensor values: {dsuid: {sensor_type: value}}
        self._device_sensor_values: dict[str, dict[int, float]] = {}

        # Per-device on/off state tracking (for individual Joker switches)
        self._device_on_states: dict[str, bool] = {}  # dsuid -> is_on

        # Metering data (PRO)
        self._circuit_power: dict[str, int] = {}  # dsuid -> watts
        self._circuits: list[dict] = []

        # Parse structure into zones and devices
        self.zones: dict[int, dict] = {}
        self.devices: dict[str, dict] = {}  # dsuid -> device info
        self._parse_structure(structure)
        self._telemetry_sent = False
        self._telemetry_last: float = 0  # timestamp of last successful ping

        # Scene discovery data
        # Key: (zone_id, group, scene_nr) -> str (user-defined name)
        self.scene_names: dict[tuple[int, int, int], str] = {}
        # Key: (zone_id, group) -> list of reachable scene numbers
        self.reachable_scenes: dict[tuple[int, int], list[int]] = {}

        # Climate data (PRO)
        self._climate_status: dict[int, dict] = {}  # zone_id -> status
        self._climate_config: dict[int, dict] = {}  # zone_id -> config

        # Apartment-wide state (PRO)
        self._apartment_presence: int | None = None  # current presence scene nr
        self._apartment_alarms: set[int] = set()     # active alarm scene nrs

        # Pro license status
        self.pro_enabled = False

    def _parse_structure(self, structure: dict) -> None:
        """Parse apartment structure into zone and device dicts."""
        apartment = structure.get("apartment", structure)

        # Parse zones
        for zone in apartment.get("zones", []):
            zone_id = zone.get("id", 0)
            if zone_id == 0 or zone_id >= 65534:
                continue

            zone_name = zone.get("name", f"Zone {zone_id}")
            devices = zone.get("devices", [])

            # Determine which groups are active in this zone
            groups = set()
            for device in devices:
                for group_entry in device.get("groups", []):
                    if isinstance(group_entry, int):
                        groups.add(group_entry)
                    elif isinstance(group_entry, dict):
                        groups.add(group_entry.get("id", 0))

            # Also check zone groups directly (include even without devices,
            # as climate control can be configured at zone level)
            for zg in zone.get("groups", []):
                gid = zg.get("group", zg.get("id", 0))
                if gid:
                    groups.add(gid)

            self.zones[zone_id] = {
                "id": zone_id,
                "name": zone_name,
                "groups": groups,
                "device_count": len(devices),
                "devices": [],  # will be populated below
            }

            # Parse devices in this zone
            for dev in devices:
                dsuid = dev.get("dSUID", dev.get("id", ""))
                if not dsuid:
                    continue
                dev_info = {
                    "dsuid": dsuid,
                    "name": dev.get("name", ""),
                    "zone_id": zone_id,
                    "zone_name": zone_name,
                    "hw_info": dev.get("hwInfo", ""),
                    "is_on": dev.get("isOn", False),
                    "output_mode": dev.get("outputMode", 0),
                    "binary_inputs": dev.get("binaryInputs", []),
                    "groups": [],
                    "sensors": [],
                }
                # Device groups
                for ge in dev.get("groups", []):
                    if isinstance(ge, int):
                        dev_info["groups"].append(ge)
                    elif isinstance(ge, dict):
                        dev_info["groups"].append(ge.get("id", 0))
                # Device sensors
                for si, sensor in enumerate(dev.get("sensors", [])):
                    dev_info["sensors"].append({
                        "index": si,
                        "type": sensor.get("type", -1),
                        "value": sensor.get("value"),
                    })
                self.devices[dsuid] = dev_info
                self.zones[zone_id]["devices"].append(dsuid)

                # Initialize device on/off state from structure (actuators + sensors)
                if GROUP_JOKER in dev_info["groups"]:
                    self._device_on_states[dsuid] = dev_info["is_on"]

    # =====================================================================
    # Scene discovery
    # =====================================================================

    async def fetch_scene_names(self) -> None:
        """Fetch scene data from dSS: reachable scenes + user-defined names.

        Uses getReachableScenes which returns both scene numbers AND names in one call.
        Falls back to sceneGetName per scene if getReachableScenes fails.
        """
        for zone_id, zone_info in self.zones.items():
            for group in zone_info["groups"]:
                if group not in SCENE_GROUPS:
                    continue
                try:
                    data = await self.api.get_reachable_scenes(zone_id, group)
                    scenes = data.get("reachableScenes", [])
                    self.reachable_scenes[(zone_id, group)] = scenes

                    # Parse user-defined names
                    for entry in data.get("userSceneNames", []):
                        nr = entry.get("sceneNr")
                        name = entry.get("sceneName", "")
                        if nr is not None and name:
                            self.scene_names[(zone_id, group, nr)] = name
                except DigitalStromApiError as err:
                    _LOGGER.debug(
                        "getReachableScenes failed for zone %d group %d: %s, trying fallback",
                        zone_id, group, err,
                    )
                    # Fallback: try individual sceneGetName calls
                    for scene_nr in [SCENE_OFF, SCENE_1, SCENE_2, SCENE_3, SCENE_4]:
                        try:
                            name = await self.api.get_scene_name(zone_id, group, scene_nr)
                            if name:
                                self.scene_names[(zone_id, group, scene_nr)] = name
                        except Exception:
                            pass
                except Exception as err:
                    _LOGGER.debug("Scene fetch error zone %d group %d: %s", zone_id, group, err)

    async def fetch_initial_states(self) -> None:
        """Fetch initial scene states for all zones via getLastCalledScene.

        Only fetch for groups that have actual devices (reduces bus load).
        """
        for zone_id, zone_info in self.zones.items():
            if not zone_info["devices"]:
                continue
            for group in zone_info["groups"]:
                if group not in (GROUP_LIGHT, GROUP_SHADE, GROUP_HEATING, GROUP_JOKER):
                    continue
                try:
                    scene = await self.api.get_last_called_scene(zone_id, group)
                    if scene >= 0:
                        is_on = scene != SCENE_OFF
                        self.set_zone_state(zone_id, group, scene=scene, is_on=is_on)
                except Exception as err:
                    _LOGGER.debug(
                        "Initial state fetch failed zone %d group %d: %s",
                        zone_id, group, err,
                    )

    async def fetch_climate_data(self) -> None:
        """Fetch climate control status and config for zones. PRO.

        Tries all zones — not just those with GROUP_HEATING/GROUP_TEMP_CONTROL,
        because some setups (PLAN44, EnOcean, external actuators) have climate
        control configured at the zone level without heating-group devices.
        """
        if not self.pro_enabled:
            return
        for zone_id, zone_info in self.zones.items():
            # Always try to fetch config (it's a cheap call that returns quickly
            # for zones without climate control)
            if zone_id not in self._climate_config:
                try:
                    config = await self.api.get_temperature_control_config(zone_id)
                    control_mode = config.get("ControlMode", 0)
                    if control_mode > 0:
                        self._climate_config[zone_id] = config
                        _LOGGER.debug(
                            "Zone %d (%s) climate config: ControlMode=%s",
                            zone_id, zone_info["name"], control_mode,
                        )
                except DigitalStromApiError:
                    pass
            # Only fetch status if zone has confirmed temp control
            if not self.has_temp_control(zone_id):
                continue
            try:
                status = await self.api.get_temperature_control_status(zone_id)
                self._climate_status[zone_id] = status
            except DigitalStromApiError:
                pass

    async def fetch_sensor_data(self) -> None:
        """Fetch apartment-wide sensor values (outdoor, per-zone). PRO."""
        if not self.pro_enabled:
            return
        try:
            data = await self.api.get_sensor_values()
            self._outdoor_sensors = data.get("outdoor", {})
            for zone_data in data.get("zones", []):
                zid = zone_data.get("id")
                if zid:
                    self._zone_sensors[zid] = zone_data
        except DigitalStromApiError:
            pass

    async def fetch_circuit_data(self) -> None:
        """Fetch dSM circuit/meter information and per-circuit power."""
        try:
            if not self._circuits:
                all_circuits = await self.api.get_circuits()
                # Only keep real dSM meters (not virtual controllers)
                self._circuits = [
                    c for c in all_circuits
                    if c.get("hwName", "").startswith("dSM")
                ]
                _LOGGER.info(
                    "Found %d dSM meters: %s",
                    len(self._circuits),
                    ", ".join(c.get("name", "") for c in self._circuits),
                )
            # Fetch per-circuit power (must query each meter individually)
            for circuit in self._circuits:
                dsuid = circuit.get("dSUID", "")
                if not dsuid:
                    continue
                try:
                    values = await self.api.get_metering_latest(
                        meter_dsuid=f".meters({dsuid})"
                    )
                    for v in values:
                        self._circuit_power[dsuid] = int(v.get("value", 0))
                except DigitalStromApiError:
                    pass
        except DigitalStromApiError as err:
            _LOGGER.debug("Circuit data fetch failed: %s", err)

    async def fetch_device_sensors(self) -> None:
        """Fetch initial device sensor values via zone/getSensorValues.

        The dSS pre-scales all values — no manual bus-encoding needed.
        After startup, real-time updates come via deviceSensorValue events
        (sensorValueFloat, also pre-scaled).
        """
        _ZONE_KEY_MAP = {
            "TemperatureValue": SENSOR_TEMPERATURE,
            "HumidityValue": SENSOR_HUMIDITY,
            "CO2concentrationValue": SENSOR_CO2,
            "BrightnessValue": SENSOR_BRIGHTNESS,
        }

        found_count = 0
        for zone_id, zone_info in self.zones.items():
            try:
                data = await self.api.get_zone_sensor_values(zone_id)
            except (DigitalStromApiError, Exception):
                continue

            for entry in data.get("values", []):
                for key, stype in _ZONE_KEY_MAP.items():
                    if key not in entry:
                        continue
                    val = round(float(entry[key]), 2)
                    # Find first device in this zone with matching sensor type
                    dsuid = self._find_device_with_sensor(zone_info, stype)
                    if dsuid:
                        self._device_sensor_values.setdefault(dsuid, {})[stype] = val
                        found_count += 1

        _LOGGER.debug("Polled %d sensor values from zone API", found_count)

    def _find_device_with_sensor(self, zone_info: dict, sensor_type: int) -> str | None:
        """Find the first device in a zone that has a given sensor type."""
        for dsuid in zone_info.get("devices", []):
            dev = self.devices.get(dsuid, {})
            for sensor in dev.get("sensors", []):
                if sensor.get("type") == sensor_type:
                    return dsuid
        return None

    def get_scene_display_name(self, zone_id: int, group: int, scene_nr: int) -> str:
        """Get display name: dS custom name or group-specific default."""
        custom = self.scene_names.get((zone_id, group, scene_nr))
        if custom:
            return custom
        if group == GROUP_SHADE:
            return NAMED_SCENES_SHADE.get(scene_nr, f"Scene {scene_nr}")
        if group == GROUP_HEATING:
            return GROUP_HEATING_SCENES.get(scene_nr, f"Scene {scene_nr}")
        return NAMED_SCENES.get(scene_nr, f"Scene {scene_nr}")

    # =====================================================================
    # State accessors
    # =====================================================================

    @property
    def consumption(self) -> int:
        return self._consumption

    @property
    def outdoor_sensors(self) -> dict:
        return self._outdoor_sensors

    @property
    def circuits(self) -> list[dict]:
        return self._circuits

    def has_temp_control(self, zone_id: int) -> bool:
        """Check if zone has temperature control vs dumb heating.

        Primary: ControlMode from getTemperatureControlConfig2 (most reliable).
        Fallback: TemperatureValue or NominalValue from getTemperatureControlValues.
        """
        # Primary: climate config ControlMode (fetched for all heating zones)
        config = self._climate_config.get(zone_id)
        if config:
            control_mode = config.get("ControlMode", 0)
            if control_mode > 0:
                return True

        # Fallback: temperature values from polling
        data = self._temperatures.get(zone_id)
        if not data:
            return False
        # Zone has temp control if it reports a measured temperature value
        tv = data.get("TemperatureValue")
        if tv is not None and tv > 0:
            return True
        # Also check if NominalValue is set (target temp configured)
        nv = data.get("NominalValue")
        if nv is not None and nv > 0:
            return True
        return False

    def get_temperature(self, zone_id: int) -> float | None:
        """Get target/nominal temperature for a zone."""
        data = self._temperatures.get(zone_id)
        if data and data.get("NominalValue", 0) > 0:
            return data["NominalValue"]
        return None

    def get_current_temperature(self, zone_id: int) -> float | None:
        """Get actual measured temperature for a zone."""
        data = self._temperatures.get(zone_id)
        if data:
            # Prefer TemperatureValue from getTemperatureControlValues
            tv = data.get("TemperatureValue")
            if tv and tv > 0:
                return tv
            # Fallback to sensor event data
            sv = data.get("sensorValue")
            if sv and sv > 0:
                return sv
        return None

    def get_any_temperature(self, zone_id: int) -> float | None:
        """Get any available temperature for a zone (regardless of temp control).

        Used for rooms that have a temperature sensor but no heating/temp control.
        Checks: TemperatureValue, sensorValue from events, device sensors.
        """
        # First try coordinator temp data
        temp = self.get_current_temperature(zone_id)
        if temp is not None:
            return temp

        # Then try device sensors in this zone
        zone_info = self.zones.get(zone_id, {})
        for dsuid in zone_info.get("devices", []):
            dev_sensors = self._device_sensor_values.get(dsuid, {})
            if SENSOR_TEMPERATURE in dev_sensors:
                return dev_sensors[SENSOR_TEMPERATURE]
        return None

    def get_control_value(self, zone_id: int) -> float | None:
        """Get heating control output value (0-100%) for a zone."""
        data = self._temperatures.get(zone_id)
        if data and "ControlValue" in data:
            return data["ControlValue"]
        return None

    def get_climate_status(self, zone_id: int) -> dict | None:
        return self._climate_status.get(zone_id)

    def get_climate_config(self, zone_id: int) -> dict | None:
        return self._climate_config.get(zone_id)

    def get_zone_sensor(self, zone_id: int) -> dict:
        return self._zone_sensors.get(zone_id, {})

    def get_circuit_power(self, dsuid: str) -> int:
        return self._circuit_power.get(dsuid, 0)

    def get_device_sensor_value(self, dsuid: str, sensor_type: int) -> float | None:
        """Get a device sensor value by type."""
        return self._device_sensor_values.get(dsuid, {}).get(sensor_type)

    def get_zone_state(self, zone_id: int, group: int) -> dict[str, Any]:
        return self._zone_states.get((zone_id, group), {"scene": None, "value": None})

    def set_zone_state(self, zone_id: int, group: int, **kwargs: Any) -> None:
        key = (zone_id, group)
        if key not in self._zone_states:
            self._zone_states[key] = {"scene": None, "value": None}
        self._zone_states[key].update(kwargs)

    def get_device_on_state(self, dsuid: str) -> bool | None:
        """Get individual device on/off state."""
        return self._device_on_states.get(dsuid)

    def set_device_on_state(self, dsuid: str, is_on: bool) -> None:
        """Set individual device on/off state."""
        self._device_on_states[dsuid] = is_on

    # Apartment state accessors (PRO)

    @property
    def apartment_presence(self) -> int | None:
        """Current presence scene number (71=Present, 72=Absent, etc.)."""
        return self._apartment_presence

    @property
    def apartment_alarms(self) -> set[int]:
        """Set of active alarm scene numbers."""
        return self._apartment_alarms

    def set_apartment_presence(self, scene: int) -> None:
        self._apartment_presence = scene

    def is_alarm_active(self, scene: int) -> bool:
        return scene in self._apartment_alarms

    async def fetch_apartment_state(self) -> None:
        """Fetch initial apartment presence state from dSS."""
        try:
            scene = await self.api.get_last_called_scene(0, 0)
            if scene >= 0 and scene in PRESENCE_SCENE_NUMBERS:
                self._apartment_presence = scene
                _LOGGER.info("Initial apartment state: scene %d", scene)
        except Exception as err:
            _LOGGER.debug("Could not fetch apartment state: %s", err)

    async def call_apartment_scene(self, scene: int) -> None:
        """Call an apartment-wide scene (zone 0, group 0)."""
        await self.api.call_scene(0, 0, scene)

    async def undo_apartment_scene(self, scene: int) -> None:
        """Undo an apartment-wide scene."""
        await self.api.undo_scene(0, 0, scene)

    def get_joker_devices_in_zone(self, zone_id: int) -> list[dict]:
        """Get all Joker (group 8) devices in a zone."""
        zone_info = self.zones.get(zone_id, {})
        result = []
        for dsuid in zone_info.get("devices", []):
            dev = self.devices.get(dsuid)
            if dev and GROUP_JOKER in dev.get("groups", []):
                result.append(dev)
        return result

    def get_joker_actuators_in_zone(self, zone_id: int) -> list[dict]:
        """Get Joker devices that are actuators (outputMode > 0)."""
        return [d for d in self.get_joker_devices_in_zone(zone_id)
                if d.get("output_mode", 0) > 0]

    def get_joker_sensors_in_zone(self, zone_id: int) -> list[dict]:
        """Get Joker devices that are sensors (outputMode == 0, have binaryInputs).

        Devices with outputMode == 0 but NO binaryInputs are wall buttons/switches
        (TKM200, TKM210, etc.) and should not appear as entities in HA.
        """
        return [d for d in self.get_joker_devices_in_zone(zone_id)
                if d.get("output_mode", 0) == 0 and d.get("binary_inputs")]

    # =====================================================================
    # Event listener
    # =====================================================================

    async def start_event_listener(self) -> None:
        """Subscribe to events and start long-poll loop."""
        try:
            await self.api.subscribe_events()
            self._reconnect_delay = RECONNECT_INITIAL
        except DigitalStromApiError as err:
            _LOGGER.error("Failed to subscribe events: %s", err)
            return

        self._event_task = self.hass.async_create_background_task(
            self._event_loop(), f"{DOMAIN}_event_loop"
        )

    async def _event_loop(self) -> None:
        """Continuously long-poll for events."""
        while True:
            try:
                events = await self.api.get_events()
                self._reconnect_delay = RECONNECT_INITIAL
                for event in events:
                    self._process_event(event)

            except DigitalStromAuthError:
                _LOGGER.warning("Auth error in event loop, reconnecting...")
                try:
                    await self.api.connect()
                    await self.api.subscribe_events()
                except DigitalStromApiError:
                    await self._backoff()

            except DigitalStromApiError as err:
                _LOGGER.warning("Event poll error: %s, retrying in %ds", err, self._reconnect_delay)
                await self._backoff()

            except asyncio.CancelledError:
                return

            except Exception:
                _LOGGER.exception("Unexpected error in event loop")
                await self._backoff()

    async def _backoff(self) -> None:
        await asyncio.sleep(self._reconnect_delay)
        self._reconnect_delay = min(self._reconnect_delay * 2, RECONNECT_MAX)

    @callback
    def _process_event(self, event: dict) -> None:
        """Process a single dSS event and update state."""
        name = event.get("name", "")
        raw_props = event.get("properties", {})

        # dSS may return properties as list of {name, value} or as dict
        if isinstance(raw_props, list):
            props = {p["name"]: p["value"] for p in raw_props if "name" in p}
        else:
            props = raw_props

        if name == "stateChange":
            _LOGGER.debug(
                "Raw stateChange event: raw_props_type=%s props=%s",
                type(raw_props).__name__, props,
            )

        if name in ("callScene", "undoScene"):
            zone_id = int(props.get("zoneID", 0))
            group = int(props.get("groupID", 0))
            scene = int(props.get("sceneID", -1))

            if scene < 0:
                return

            # Apartment-level scenes (zone 0)
            if zone_id == 0:
                if name == "callScene":
                    if scene in PRESENCE_SCENE_NUMBERS:
                        self._apartment_presence = scene
                    elif scene in ALARM_SCENE_NUMBERS:
                        self._apartment_alarms.add(scene)
                elif name == "undoScene":
                    if scene in ALARM_SCENE_NUMBERS:
                        self._apartment_alarms.discard(scene)
                _LOGGER.debug(
                    "Apartment event %s: scene=%d (presence=%s, alarms=%s)",
                    name, scene, self._apartment_presence, self._apartment_alarms,
                )
                self.async_update_listeners()
                return

            if zone_id > 0:
                is_on = scene != SCENE_OFF if name == "callScene" else True
                self.set_zone_state(zone_id, group, scene=scene, is_on=is_on)

                # Update individual device states for Joker group scenes
                if group == GROUP_JOKER:
                    for dev in self.get_joker_devices_in_zone(zone_id):
                        self.set_device_on_state(dev["dsuid"], is_on)

                _LOGGER.debug(
                    "Event %s: zone=%d group=%d scene=%d",
                    name, zone_id, group, scene,
                )
                self.async_update_listeners()

        elif name == "zoneSensorValue":
            zone_id = int(props.get("zoneID", 0))
            sensor_type = int(props.get("sensorType", -1))
            # Prefer sensorValueFloat (properly scaled) over sensorValue (raw integer)
            value = props.get("sensorValueFloat", props.get("sensorValue"))

            if zone_id and value is not None:
                if zone_id not in self._temperatures:
                    self._temperatures[zone_id] = {}
                self._temperatures[zone_id]["sensorValue"] = float(value)
                self._temperatures[zone_id]["sensorType"] = sensor_type
                self.async_update_listeners()

        elif name == "deviceSensorValue":
            dsuid = props.get("dsuid", "")
            sensor_type = int(props.get("sensorType", -1))
            # Prefer sensorValueFloat (properly scaled) over sensorValue (raw integer)
            value = props.get("sensorValueFloat", props.get("sensorValue"))
            if dsuid and value is not None:
                # Update device sensor values cache
                if dsuid not in self._device_sensor_values:
                    self._device_sensor_values[dsuid] = {}
                self._device_sensor_values[dsuid][sensor_type] = float(value)

                # Also update device info sensors
                if dsuid in self.devices:
                    dev = self.devices[dsuid]
                    for s in dev.get("sensors", []):
                        if s.get("type") == sensor_type:
                            s["value"] = float(value)
                            break
                self.async_update_listeners()

        elif name == "stateChange":
            dsuid = props.get("dsuid", "")
            state_name = props.get("statename", "")
            state_value = props.get("state", "")

            # Apartment-level state changes (rain, etc.) — no dsuid
            # dSS format: StateApartment;rain;1;active / StateApartment;rain;2;inactive
            if state_name == "rain":
                is_active = state_value.lower() in ("active", "true", "1")
                if is_active:
                    self._apartment_alarms.add(SCENE_RAIN)
                else:
                    self._apartment_alarms.discard(SCENE_RAIN)
                _LOGGER.debug(
                    "Apartment state change: %s=%s (alarms=%s)",
                    state_name, state_value, self._apartment_alarms,
                )
                self.async_update_listeners()
            elif dsuid and dsuid in self.devices:
                # Binary input state changes (contacts, smoke, etc.)
                is_active = state_value in ("active", "true", "1", "open")
                self.set_device_on_state(dsuid, is_active)
                _LOGGER.debug(
                    "State change: dsuid=%s state=%s value=%s",
                    dsuid[:8], state_name, state_value,
                )
                self.async_update_listeners()

    # =====================================================================
    # Polling (DataUpdateCoordinator)
    # =====================================================================

    async def _async_update_data(self) -> dict:
        """Periodic poll for consumption + temperature + sensors."""
        try:
            self._consumption = await self.api.get_consumption()

            temp_data = await self.api.get_temperature_values()
            for zone_data in temp_data:
                zone_id = zone_data.get("id")
                if zone_id is not None and zone_id > 0:
                    # Merge with existing data (preserve sensorValue from events)
                    existing = self._temperatures.get(zone_id, {})
                    existing.update(zone_data)
                    self._temperatures[zone_id] = existing

            # Per-circuit power (FREE)
            await self.fetch_circuit_data()

            # Device sensors: Ulux, thermostats, etc. (FREE)
            await self.fetch_device_sensors()

            # Pro features: extra data
            if self.pro_enabled:
                await self.fetch_sensor_data()
                await self.fetch_climate_data()

        except DigitalStromAuthError:
            _LOGGER.warning("Auth error during poll, reconnecting...")
            try:
                await self.api.connect()
            except DigitalStromApiError as err:
                raise UpdateFailed(f"Re-auth failed: {err}") from err

        except DigitalStromApiError as err:
            raise UpdateFailed(f"Poll failed: {err}") from err

        # Send anonymous telemetry ping (at startup + every 24h)
        now = _time.time()
        if not self._telemetry_sent or (now - self._telemetry_last > 86400):
            self._telemetry_sent = True
            self._telemetry_last = now
            self.hass.async_create_task(self._send_telemetry())

        return {
            "consumption": self._consumption,
            "temperatures": self._temperatures,
        }

    async def _send_telemetry(self) -> None:
        """Send anonymous ping to WoonIoT (best-effort, retry on fail)."""
        # Get HA version safely
        try:
            from homeassistant.const import __version__ as ha_version
        except ImportError:
            ha_version = "unknown"
        payload = {
            "v": INTEGRATION_VERSION,
            "zones": len(self.zones),
            "devices": len(self.devices),
            "dss_id": self.dss_id[:8] if self.dss_id else "",
            "ha": ha_version,
            "pro": self.pro_enabled,
        }
        # Try up to 3 times with increasing delay
        for attempt in range(3):
            try:
                # ssl=False to skip SSL verification without blocking call
                conn = aiohttp.TCPConnector(ssl=False)
                async with aiohttp.ClientSession(connector=conn) as session:
                    async with session.post(
                        TELEMETRY_URL,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status == 200:
                            _LOGGER.debug("Telemetry ping sent successfully")
                            return
                        _LOGGER.debug("Telemetry ping HTTP %d", resp.status)
            except Exception as err:
                _LOGGER.debug("Telemetry ping attempt %d failed: %s", attempt + 1, err)
            # Wait before retry (30s, 60s)
            if attempt < 2:
                await asyncio.sleep(30 * (attempt + 1))

    async def shutdown(self) -> None:
        """Clean shutdown."""
        if self._event_task and not self._event_task.done():
            self._event_task.cancel()
            try:
                await self._event_task
            except asyncio.CancelledError:
                pass
        await self.api.close()
