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
    GROUP_TEMP_CONTROL,
    SCENE_OFF,
    SCENE_1,
    SCENE_2,
    SCENE_3,
    SCENE_4,
    NAMED_SCENES,
    NAMED_SCENES_SHADE,
    GROUP_HEATING_SCENES,
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
        self._paused = False
        self._reconnect_delay = RECONNECT_INITIAL

        # State tracking: {(zone_id, group): {"scene": int, "value": int, "is_on": bool}}
        self._zone_states: dict[tuple[int, int], dict[str, Any]] = {}

        # Sensor data
        self._consumption: int = 0
        self._temperatures: dict[int, dict] = {}  # zone_id -> temp data
        self._outdoor_sensors: dict = {}  # outdoor weather data
        self._zone_sensors: dict[int, dict] = {}  # zone_id -> sensor readings

        # Metering data (PRO)
        self._circuit_power: dict[str, int] = {}  # dsuid -> watts
        self._circuits: list[dict] = []

        # Parse structure into zones and devices
        self.zones: dict[int, dict] = {}
        self.devices: dict[str, dict] = {}  # dsuid -> device info
        self._parse_structure(structure)
        self._telemetry_sent = False

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
        """Fetch initial scene states for all zones via getLastCalledScene."""
        for zone_id, zone_info in self.zones.items():
            for group in zone_info["groups"]:
                if group not in (GROUP_LIGHT, GROUP_SHADE, GROUP_HEATING):
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
            self._circuits = await self.api.get_circuits()
            values = await self.api.get_metering_latest()
            for v in values:
                dsuid = v.get("dSUID", "")
                if dsuid:
                    self._circuit_power[dsuid] = v.get("value", 0)
        except DigitalStromApiError:
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
    def is_paused(self) -> bool:
        return self._paused

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
        """Check if zone has temperature control (group 48) vs dumb heating."""
        zone = self.zones.get(zone_id)
        if not zone:
            return False
        return GROUP_TEMP_CONTROL in zone["groups"]

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

    def get_zone_state(self, zone_id: int, group: int) -> dict[str, Any]:
        return self._zone_states.get((zone_id, group), {"scene": None, "value": None})

    def set_zone_state(self, zone_id: int, group: int, **kwargs: Any) -> None:
        key = (zone_id, group)
        if key not in self._zone_states:
            self._zone_states[key] = {"scene": None, "value": None}
        self._zone_states[key].update(kwargs)

    # =====================================================================
    # Event listener
    # =====================================================================

    async def start_event_listener(self) -> None:
        """Subscribe to events and start long-poll loop."""
        if self._paused:
            return
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
        while not self._paused:
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
            if dsuid and dsuid in self.devices and value is not None:
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
        if self._paused:
            raise UpdateFailed("Integration is paused")

        try:
            self._consumption = await self.api.get_consumption()

            temp_data = await self.api.get_temperature_values()
            for zone_data in temp_data:
                zone_id = zone_data.get("id")
                if zone_id:
                    self._temperatures[zone_id] = zone_data

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

        # Send anonymous telemetry ping (once per startup)
        if not self._telemetry_sent:
            self._telemetry_sent = True
            self.hass.async_create_task(self._send_telemetry())

        return {
            "consumption": self._consumption,
            "temperatures": self._temperatures,
        }

    # =====================================================================
    # Pause / Resume
    # =====================================================================

    async def pause(self) -> None:
        """Pause all dSS communication (for dS Configurator use)."""
        _LOGGER.info("Pausing Digital Strom communication")
        self._paused = True

        if self._event_task and not self._event_task.done():
            self._event_task.cancel()
            try:
                await self._event_task
            except asyncio.CancelledError:
                pass
            self._event_task = None

        self.async_update_listeners()

    async def resume(self) -> None:
        """Resume communication and re-sync state."""
        _LOGGER.info("Resuming Digital Strom communication")
        self._paused = False

        try:
            await self.api.connect()

            # Re-fetch structure in case config changed
            structure = await self.api.get_structure()
            self._parse_structure(structure)

            # Re-fetch scene names and initial states
            await self.fetch_scene_names()
            await self.fetch_initial_states()

            # Restart event listener
            await self.start_event_listener()

            # Force immediate data poll
            await self.async_request_refresh()

        except DigitalStromApiError as err:
            _LOGGER.error("Failed to resume: %s", err)

    async def _send_telemetry(self) -> None:
        """Send anonymous ping to WoonIoT (once per startup, best-effort)."""
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    TELEMETRY_URL,
                    json={
                        "v": INTEGRATION_VERSION,
                        "zones": len(self.zones),
                        "devices": len(self.devices),
                        "dss_id": self.dss_id[:8] if self.dss_id else "",
                        "ha": self.hass.config.version,
                        "pro": self.pro_enabled,
                    },
                    timeout=aiohttp.ClientTimeout(total=5),
                )
        except Exception:
            pass  # Telemetry is best-effort, never fail

    async def shutdown(self) -> None:
        """Clean shutdown."""
        self._paused = True
        if self._event_task and not self._event_task.done():
            self._event_task.cancel()
            try:
                await self._event_task
            except asyncio.CancelledError:
                pass
        await self.api.close()
