"""Event listener and data coordinator for digitalSTROM."""

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


class DigitalStromCoordinator(DataUpdateCoordinator):
    """Coordinator: manages event listener + periodic polling."""

    def __init__(self, hass: HomeAssistant, api: DigitalStromApi, structure: dict, dss_id: str = "") -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=POLL_INTERVAL_ENERGY),
        )
        self.api = api
        self._structure = structure
        self.dss_id = dss_id
        self._event_task: asyncio.Task | None = None
        self._paused = False
        self._reconnect_delay = RECONNECT_INITIAL

        # State tracking: {(zone_id, group): {"scene": int, "value": int}}
        self._zone_states: dict[tuple[int, int], dict[str, Any]] = {}

        # Sensor data
        self._consumption: int = 0
        self._temperatures: dict[int, dict] = {}  # zone_id -> temp data

        # Parse structure into zones
        self.zones: dict[int, dict] = {}
        self._parse_structure(structure)
        self._telemetry_sent = False

        # Scene names from dS (populated async via fetch_scene_names)
        # Key: (zone_id, group, scene_nr) -> str
        self.scene_names: dict[tuple[int, int, int], str] = {}

    def _parse_structure(self, structure: dict) -> None:
        """Parse apartment structure into zone dict."""
        apartment = structure.get("apartment", structure)
        for zone in apartment.get("zones", []):
            zone_id = zone.get("id", 0)
            if zone_id == 0 or zone_id >= 65534:
                continue  # Skip zone 0 (apartment-level) and 65534 (unassigned)

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
            }

    async def fetch_scene_names(self) -> None:
        """Fetch user-defined scene names from dSS for all zones/groups."""
        scene_numbers = [SCENE_OFF, SCENE_1, SCENE_2, SCENE_3, SCENE_4]
        for zone_id, zone_info in self.zones.items():
            for group in zone_info["groups"]:
                if group not in (GROUP_LIGHT, GROUP_SHADE, GROUP_HEATING):
                    continue
                for scene_nr in scene_numbers:
                    try:
                        name = await self.api.get_scene_name(zone_id, group, scene_nr)
                        if name:
                            self.scene_names[(zone_id, group, scene_nr)] = name
                    except Exception:
                        pass

    def get_scene_display_name(self, zone_id: int, group: int, scene_nr: int) -> str:
        """Get display name for a scene: dS custom name, or fallback to default."""
        # First check dS custom name
        custom = self.scene_names.get((zone_id, group, scene_nr))
        if custom:
            return custom
        # Fallback to group-specific defaults
        if group == GROUP_SHADE:
            return NAMED_SCENES_SHADE.get(scene_nr, f"Scene {scene_nr}")
        if group == GROUP_HEATING:
            return GROUP_HEATING_SCENES.get(scene_nr, f"Scene {scene_nr}")
        return NAMED_SCENES.get(scene_nr, f"Scene {scene_nr}")

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def consumption(self) -> int:
        return self._consumption

    def get_temperature(self, zone_id: int) -> float | None:
        data = self._temperatures.get(zone_id)
        if data and data.get("NominalValue", 0) > 0:
            return data["NominalValue"]
        return None

    def get_zone_state(self, zone_id: int, group: int) -> dict[str, Any]:
        return self._zone_states.get((zone_id, group), {"scene": None, "value": None})

    def set_zone_state(self, zone_id: int, group: int, **kwargs: Any) -> None:
        key = (zone_id, group)
        if key not in self._zone_states:
            self._zone_states[key] = {"scene": None, "value": None}
        self._zone_states[key].update(kwargs)

    # --- Event listener ---

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

        self._event_task = self.hass.async_create_task(
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

        elif name == "stateChange":
            _LOGGER.debug("State change: %s", props)

    # --- Polling (DataUpdateCoordinator) ---

    async def _async_update_data(self) -> dict:
        """Periodic poll for consumption + temperature."""
        if self._paused:
            raise UpdateFailed("Integration is paused")

        try:
            self._consumption = await self.api.get_consumption()

            temp_data = await self.api.get_temperature_values()
            for zone_data in temp_data:
                zone_id = zone_data.get("id")
                if zone_id:
                    self._temperatures[zone_id] = zone_data

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

    # --- Pause / Resume ---

    async def pause(self) -> None:
        """Pause all dSS communication (for dS Configurator use)."""
        _LOGGER.info("Pausing digitalSTROM communication")
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
        _LOGGER.info("Resuming digitalSTROM communication")
        self._paused = False

        try:
            await self.api.connect()

            # Re-fetch structure in case config changed
            structure = await self.api.get_structure()
            self._parse_structure(structure)

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
                        "dss_id": self.dss_id[:8] if self.dss_id else "",
                        "ha": self.hass.config.version,
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
