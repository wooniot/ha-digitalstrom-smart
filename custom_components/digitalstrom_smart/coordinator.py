"""Event listener and data coordinator for Digital Strom.

Central hub: manages event subscriptions, periodic polling,
scene discovery, sensor data, and state tracking.
"""

import asyncio
import logging
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

            # Also check zone groups directly
            for zg in zone.get("groups", []):
                gid = zg.get("group", zg.get("id", 0))
                if gid and zg.get("devices", []):
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

                # Initialize device on/off state from structure
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
        """Fetch climate control status and config for heating zones. PRO."""
        if not self.pro_enabled:
            return
        for zone_id, zone_info in self.zones.items():
            if GROUP_HEATING not in zone_info["groups"] and GROUP_TEMP_CONTROL not in zone_info["groups"]:
                continue
            # Only fetch if zone has temp control (not dumb heating)
            if not self.has_temp_control(zone_id):
                continue
            try:
                status = await self.api.get_temperature_control_status(zone_id)
                self._climate_status[zone_id] = status
            except DigitalStromApiError:
                pass
            try:
                config = await self.api.get_temperature_control_config(zone_id)
                self._climate_config[zone_id] = config
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
        """Fetch circuit/meter information. PRO."""
        if not self.pro_enabled:
            return
        try:
            if not self._circuits:
                self._circuits = await self.api.get_circuits()
            # Fetch per-circuit power
            values = await self.api.get_metering_latest()
            for v in values:
                dsuid = v.get("dSUID", "")
                if dsuid:
                    self._circuit_power[dsuid] = v.get("value", 0)
        except DigitalStromApiError:
            pass

    async def fetch_device_sensors(self) -> None:
        """Fetch sensor values from devices that have sensors (Ulux, etc.).

        Only fetches for devices with relevant sensor types (temp, CO2, brightness, humidity).
        Called once at startup and then relies on deviceSensorValue events.
        """
        relevant_types = {SENSOR_TEMPERATURE, SENSOR_HUMIDITY, SENSOR_BRIGHTNESS, SENSOR_CO2}
        for dsuid, dev in self.devices.items():
            for sensor in dev.get("sensors", []):
                stype = sensor.get("type", -1)
                if stype not in relevant_types:
                    continue
                try:
                    result = await self.api.get_device_sensor_value(dsuid, sensor["index"])
                    value = result.get("value")
                    if value is not None:
                        if dsuid not in self._device_sensor_values:
                            self._device_sensor_values[dsuid] = {}
                        self._device_sensor_values[dsuid][stype] = float(value)
                        sensor["value"] = float(value)
                except DigitalStromApiError:
                    _LOGGER.debug("Failed to fetch sensor %d from device %s", sensor["index"], dsuid[:8])
                except Exception:
                    pass

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

        Detection: if getTemperatureControlValues returns TemperatureValue
        for this zone, it has active temperature control. Group 48 is a
        virtual group that may not appear in device groups.
        """
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

    def get_joker_devices_in_zone(self, zone_id: int) -> list[dict]:
        """Get all Joker (group 8) devices in a zone."""
        zone_info = self.zones.get(zone_id, {})
        result = []
        for dsuid in zone_info.get("devices", []):
            dev = self.devices.get(dsuid)
            if dev and GROUP_JOKER in dev.get("groups", []):
                result.append(dev)
        return result

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
        props = event.get("properties", {})

        if name in ("callScene", "undoScene"):
            zone_id = int(props.get("zoneID", 0))
            group = int(props.get("groupID", 0))
            scene = int(props.get("sceneID", -1))

            if zone_id and scene >= 0:
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
            value = props.get("sensorValue")

            if zone_id and value is not None:
                if zone_id not in self._temperatures:
                    self._temperatures[zone_id] = {}
                self._temperatures[zone_id]["sensorValue"] = float(value)
                self._temperatures[zone_id]["sensorType"] = sensor_type
                self.async_update_listeners()

        elif name == "deviceSensorValue":
            dsuid = props.get("dsuid", "")
            sensor_type = int(props.get("sensorType", -1))
            value = props.get("sensorValue")
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
            _LOGGER.debug("State change: %s", props)

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
                if zone_id:
                    # Merge with existing data (preserve sensorValue from events)
                    existing = self._temperatures.get(zone_id, {})
                    existing.update(zone_data)
                    self._temperatures[zone_id] = existing

            # Pro features: extra data
            if self.pro_enabled:
                await self.fetch_sensor_data()
                await self.fetch_climate_data()
                await self.fetch_circuit_data()

        except DigitalStromAuthError:
            _LOGGER.warning("Auth error during poll, reconnecting...")
            try:
                await self.api.connect()
            except DigitalStromApiError as err:
                raise UpdateFailed(f"Re-auth failed: {err}") from err

        except DigitalStromApiError as err:
            raise UpdateFailed(f"Poll failed: {err}") from err

        # Send anonymous telemetry ping (at startup + every 24h)
        import time as _time
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
