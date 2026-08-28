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
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DigitalStromApi, DigitalStromApiError, DigitalStromAuthError
from .license import check_pro_license, sync_pro_issue
import aiohttp

from .const import (
    DOMAIN,
    BUTTON_FUNCTION_IDS,
    signal_button_event,
    POLL_INTERVAL_ENERGY,
    POLL_INTERVAL_BINARY,
    POLL_INTERVAL_VANGNET,
    RECONNECT_INITIAL,
    RECONNECT_MAX,
    GROUP_LIGHT,
    GROUP_SHADE,
    GROUP_HEATING,
    GROUP_JOKER,
    GROUP_COOLING,
    GROUP_VENTILATION,
    GROUP_HOME_VENTILATION,
    GROUP_TEMP_CONTROL,
    VENTILATION_OUTPUT_OFFSETS,
    VENTILATION_ON_THRESHOLD_PCT,
    UMR200_HW_MARKER,
    UMR200_OFFSET_FAIL_LIMIT,
    ZONE_LEVEL_GROUPS,
    SCENE_OFF,
    SCENE_1,
    SCENE_2,
    SCENE_3,
    SCENE_4,
    AREA_ON_SCENES,
    AREA_OFF_SCENES,
    ALL_ZONE_SCENES,
    NAMED_SCENES,
    NAMED_SCENES_SHADE,
    GROUP_HEATING_SCENES,
    AREA_SCENE_NAMES,
    APARTMENT_SYSTEM_STATES,
    APARTMENT_ENV_STATES,
    MOTION_STATE_RE,
    SENSOR_TEMPERATURE,
    SENSOR_HUMIDITY,
    SENSOR_BRIGHTNESS,
    SENSOR_CO2,
    INTEGRATION_VERSION,
    TELEMETRY_URL,
    PRESENCE_SCENE_NUMBERS,
    ALARM_SCENE_NUMBERS,
    SCENE_PRESENT,
    SCENE_RAIN,
    USER_ACTION_SOURCE,
    SKIP_USER_STATES,
    STATE_VALUE_ACTIVE,
    SENSOR_ACTIVE_POWER,
    SENSOR_ACTIVE_ENERGY,
)

_LOGGER = logging.getLogger(__name__)

# Groups for which we create scene entities
SCENE_GROUPS = (GROUP_LIGHT, GROUP_SHADE, GROUP_HEATING)

# Bij (her)start heeft de dSS de ds485-bus nog niet herscand; getState kan dan een
# pre-settle 'false' geven voor een Joker-ACTOR die fysiek AAN staat. We wachten deze
# tijd voordat we een dubieuze 'false'-seed bevestigen (René, SW-KL, 22 aug 2026).
JOKER_STARTUP_SETTLE_SECONDS = 5


def _is_climate_control_active(control_mode) -> bool:
    """Check if a ControlMode value indicates active climate control.

    dSS returns ControlMode as int (0=off, 1=PID, 11=cooling, etc.)
    or as string ("control", "pid", etc.) depending on firmware.
    """
    if control_mode is None or control_mode == "" or control_mode == 0:
        return False
    if isinstance(control_mode, (int, float)):
        return control_mode > 0
    if isinstance(control_mode, str):
        if control_mode in ("0", "off", ""):
            return False
        return True  # any other string = active
    return False


class DigitalStromCoordinator(DataUpdateCoordinator):
    """Coordinator: manages event listener + periodic polling."""

    def __init__(
        self, hass: HomeAssistant, api: DigitalStromApi,
        structure: dict, dss_id: str = "",
        main_poll_interval: int = POLL_INTERVAL_ENERGY,
        binary_poll_interval: int = POLL_INTERVAL_BINARY,
    ) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(seconds=main_poll_interval),
        )
        self.api = api
        self._structure = structure
        self.dss_id = dss_id
        # User-tunable dSS request rate (Options flow). The binary fallback poll
        # is the dominant steady-state load; events keep the fast path instant.
        self._binary_poll_interval = binary_poll_interval
        self._event_task: asyncio.Task | None = None
        self._binary_poll_task: asyncio.Task | None = None
        self._reconnect_delay = RECONNECT_INITIAL

        # Vangnet-cadans voor de joker-actor live-confirm + climate-status-poll.
        # Beide zijn alleen vangnet (events houden ze tussendoor live), dus draaien
        # ze op ~1×/min i.p.v. elke hoofdcyclus. De drempel is het vangnet-interval
        # minus een halve hoofdcyclus, zodat het op de default 30s-poll robuust op
        # elke twééde cyclus valt (i.p.v. door scheduler-drift naar 90s te springen).
        # Nooit trager dan de hoofdcyclus zelf (als de user die > 60s zet).
        self._vangnet_interval = max(POLL_INTERVAL_VANGNET, main_poll_interval)
        self._vangnet_due_threshold = self._vangnet_interval - main_poll_interval / 2
        self._last_joker_confirm: float = 0.0   # throttle joker-actor live-confirm
        self._last_climate_poll: float = 0.0    # throttle per-zone climate-status

        # State tracking: {(zone_id, group): {"scene": int, "value": int, "is_on": bool}}
        self._zone_states: dict[tuple[int, int], dict[str, Any]] = {}
        # Area-besef voor zone is_on (#26): welke areas binnen een zone aan staan,
        # en of de zone via een hele-zone-preset aan is gezet. Een DS area-uit-scene
        # (1-4) zet maar één area uit -> de zone is pas echt uit als alle areas uit zijn.
        self._zone_areas_on: dict[tuple[int, int], set[int]] = {}
        self._zone_broadcast_on: dict[tuple[int, int], bool] = {}

        # Sensor data
        self._consumption: int = 0
        self._temperatures: dict[int, dict] = {}  # zone_id -> temp data
        self._outdoor_sensors: dict = {}  # outdoor weather data
        self._zone_sensors: dict[int, dict] = {}  # zone_id -> sensor readings
        # True only while THIS poll cycle's apartment getSensorValues succeeded.
        # Reset at the start of every _async_update_data; lets fetch_device_sensors
        # map the fresh apartment cache exactly once, and fall back to the per-zone
        # vangnet loop if the apartment fetch structurally fails (René, 26 aug 2026).
        self._zone_sensors_fresh: bool = False

        # Device sensor values: {dsuid: {sensor_type: value}}
        self._device_sensor_values: dict[str, dict[int, float]] = {}
        self._last_power_poll: float = 0.0  # throttle SW-series power refresh to 30s

        # Per-device on/off state tracking.
        # _device_on_states    = de OUTPUT/relais-stand van een Joker-ACTOR (leest de switch).
        # _device_input_states = de BINAIRE-INGANG-stand (leest de binary_sensor).
        # Ze zijn GESCHEIDEN zodat een Joker-actor MET ingang (bv. SW-KL200 e-radiator) niet
        # twee betekenissen in één slot propt — anders overschrijft de ingang-status na een
        # herstart de relais-stand (switch toont 'aan' terwijl de actor uit is) en andersom
        # overschrijft een scene-wissel de ingang-sensor. (René, SW-KL, 21 aug 2026.)
        self._device_on_states: dict[str, bool] = {}  # dsuid -> output on/off (switch)
        self._device_input_states: dict[str, bool] = {}  # dsuid -> binary input active (sensor)
        # Joker-actoren waarvoor de runtime-divergentie (isOn=true maar getOutputValue=0)
        # AL met WARNING gemeld is. Een blijvende divergentie herstelt elke poll opnieuw —
        # correct, maar zonder deze rem zou elke 30s-cyclus een nieuwe WARNING geven en
        # HA een terugkerende 'fout uit aangepaste integratie'-banner tonen (René, SW-KL,
        # 23 aug 2026). We waarschuwen daarom één keer per episode; zolang de divergentie
        # aanhoudt zakt het naar debug. Zodra de actor weer klopt (out>0 of geen isOn),
        # verwijderen we de dsuid zodat een NIEUWE episode later weer één WARNING geeft.
        self._joker_divergence_warned: set[str] = set()
        # Per-device runtime output status from apartment/getDevices: {dsuid: {"on", "is_present", "is_valid"}}
        self._device_runtime: dict[str, dict] = {}
        # SW-UMR200 ventilation outputs: {dsuid: {offset: {"raw": 0..255, "pct": 0..100}}}
        # Filled from getOutputValue per output offset — the direct relay read.
        self._ventilation_outputs: dict[str, dict[int, dict]] = {}

        # Metering data
        self._circuit_power: dict[str, int] = {}  # dsuid -> watts
        self._circuit_energy_wh: dict[str, int] = {}  # dsuid -> cumulative Wh (normalised)
        self._circuits: list[dict] = []

        # User Defined Actions & States (apartment automation primitives)
        self._user_actions: list[dict] = []   # [{"id", "name", "source", "disabled"}]
        self._user_states: dict[str, dict] = {}   # name -> {"state", "value"}
        # Configurator-defined custom states (the "real" user defined states)
        # id -> {"name", "set_name", "reset_name", "state", "value"}
        self._custom_states: dict[str, dict] = {}
        # Configurator timers / "klokken" (system-addon-timed-events)
        # id -> {"name", "last_executed", "enabled", "time_base", "offset", ...}
        self._timed_events: dict[str, dict] = {}

        # dsuids whose raw getStructure entry we already dumped once (beta38
        # UMR200 group-diagnostic). Must be initialised BEFORE _parse_structure
        # runs — the diagnostic gate in _parse_structure reads it (beta39 fix:
        # beta38 crashed on setup with AttributeError because this set was only
        # created further down, after the parse call).
        self._umr200_raw_logged: set[str] = set()

        # dsuid/offset pairs whose STARTUP seed trio we already dumped once
        # (beta40 SEED-DIAG). René (28 aug 2026): a Woningventilatie UMR200 output
        # shows a wrong INITIAL value right after a restart, then self-corrects.
        # These outputs are group 8 (Joker) + 64, so they seed from TWO sources at
        # boot — getState.isOn (the Joker control switch) and getOutputValue (the
        # ventilation-status sensor). To see which source is wrong at boot without
        # asking René to enable full debug, log both side by side once per session.
        self._umr200_seed_logged: set[str] = set()

        # dsuid/offset pairs confirmed to NOT exist on this UMR200 (getOutputValue
        # keeps returning a dS485 bus error -- "invalid parameter", i.e. that relay
        # channel is not wired on this module). Single-output UMR200 actors only
        # populate offset 0; VENTILATION_OUTPUT_OFFSETS unconditionally probes
        # offset 1 too, so every vangnet cycle (~1x/min) sent a doomed command onto
        # the live dS485 bus for every such device. After UMR200_OFFSET_FAIL_LIMIT
        # consecutive failures for the same dsuid/offset we stop asking -- a single
        # transient dSS hiccup does not blacklist a real offset (René, 28 aug 2026).
        self._umr200_offset_fail_counts: dict[str, int] = {}
        self._umr200_bad_offsets: set[str] = set()

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
        # Zones die ooit temp-control bleken → blijven gepolld, ook als de dSS
        # in koelmodus ControlMode=0 teruggeeft (anders verdwijnt de regelwaarde/
        # setpoint zodra het systeem naar koelen schakelt).
        self._temp_control_zones: set[int] = set()
        self._climate_config: dict[int, dict] = {}  # zone_id -> config
        # Zones met een succesvolle config-call ZONDER actieve klimaatregeling.
        # Voorkomt dat fetch_climate_data() zulke zones elke vangnet-cyclus
        # opnieuw bevraagt (getTemperatureControlConfig2) — het antwoord
        # ('mode': 'off') verandert niet tijdens de levensduur van de
        # coordinator. Een mislukte call belandt hier NIET in, zodat een
        # tijdelijke dSS-hapering volgende cyclus gewoon opnieuw wordt
        # geprobeerd (René, 26 aug 2026).
        self._climate_config_checked: set[int] = set()

        # Apartment-wide state (PRO)
        self._apartment_presence: int | None = None  # current presence scene nr
        self._apartment_alarms: set[int] = set()     # active alarm scene nrs
        self._apartment_states: dict[str, bool] = {} # dSS system states: name -> active
        self._motion_zones: list[int] = []           # zones with a zone.X.motion state (PRO)
        self._malfunction_names: list[str] = []       # zone.X.group.N.status.malfunction (PRO)
        self._service_names: list[str] = []           # zone.X.group.N.status.service (PRO)
        self._outdoor: dict[str, float] = {}          # weather-service: temperature/sun (PRO)
        self._heating_system_cooling: bool = False    # True when system is in cooling mode
        self._heating_mode_initialized: bool = False  # fetched at least once from API

        # Pro license status
        self.pro_enabled = False
        self.license_info: dict = {"valid": False, "reason": "no_key", "type": None, "method": None}
        # Set by async_setup_entry; used for periodic re-validation (picks up a
        # server-side license rebind without needing an HA restart).
        self.pro_license_key: str = ""
        self.entry_id: str | None = None
        self._license_last_check: float = 0.0

        # Opt-in whitelist of UMR200 output dsuids that drive ventilation but do
        # NOT surface GROUP_VENTILATION (10) in their device groups array — e.g.
        # René's Woningventilatie outputs, configured blue/Woningventilatie in
        # the dSS yet reporting only group 8 in config_group. Set from the
        # options flow (CONF_EXTRA_VENTILATION_DSUIDS). Empty by default → the
        # strict GROUP_VENTILATION gate stays in force.
        self.extra_ventilation_dsuids: set[str] = set()

    def button_devices(self) -> dict[str, dict]:
        """Devices that emit dSS ``buttonClick`` events (rockers / pushbuttons).

        Identified by dSS ``functionID`` because ``buttonInputs`` is not reliably
        populated for bridged plan44/EnOcean rocker devices. Keyed by dSUID.
        """
        return {
            dsuid: dev
            for dsuid, dev in self.devices.items()
            if dev.get("function_id") in BUTTON_FUNCTION_IDS
        }

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

            # Also check zone groups directly, but ONLY for climate/HVAC groups
            # (heating/cooling/ventilation/temp-control): those can be configured
            # at zone level without a dedicated actuator device. Every other group
            # (shade, light, audio, ...) requires a real device, so it must come
            # from the device loop above — otherwise the dSS zone-group list adds
            # e.g. GROUP_SHADE to rooms that have no blinds at all, creating phantom
            # cover entities (reported by René, rooms zonder raambekleding).
            for zg in zone.get("groups", []):
                gid = zg.get("group", zg.get("id", 0))
                if gid in ZONE_LEVEL_GROUPS:
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
                    "function_id": dev.get("functionID"),
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

                # beta38 UMR200 group-diagnostic (René, 28 aug 2026): dump the
                # RAW getStructure entry for every UMR200 once, at INFO, so a
                # "Woningventilatie" output that does NOT report GROUP_VENTILATION
                # (10) reveals what the dSS actually returns — the untransformed
                # groups array (dicts may carry more than id), functionID,
                # outputMode and any system-function / apartment-level field.
                # This is the exact data needed to decide between a second group
                # constant (GROUP_HOME_VENTILATION / Recirculation 12) and reading
                # the output-channel group elsewhere in the response. One line per
                # dsuid per session → no log flood.
                if (UMR200_HW_MARKER in dev_info["hw_info"]
                        and dsuid not in self._umr200_raw_logged):
                    self._umr200_raw_logged.add(dsuid)
                    _LOGGER.info(
                        "UMR200 RAW-DIAG %s (%s | zone '%s'): "
                        "raw_groups=%s functionID=%s outputMode=%s all_keys=%s",
                        dsuid, dev.get("name", ""), zone_name,
                        dev.get("groups"), dev.get("functionID"),
                        dev.get("outputMode"), sorted(dev.keys()),
                    )

                self.zones[zone_id]["devices"].append(dsuid)

                # Initialize device on/off state from structure
                if GROUP_JOKER in dev_info["groups"]:
                    om = int(dev_info.get("output_mode", 0) or 0)
                    bi = dev_info.get("binary_inputs", [])
                    # Binaire ingang → INPUT-slot (leest de binary_sensor), NIET de switch.
                    # dSS state values: 1=active, 2=inactive (NOT 0/1!)
                    if bi and "state" in bi[0]:
                        self._device_input_states[dsuid] = (bi[0]["state"] == 1)
                    # Aan/uit van de ACTOR (switch) → OUTPUT-slot. Bij een actor (om>0) NIET
                    # uit de structuur/bulk-cache (dev["on"]/isOn) seeden — die is stale vlak
                    # na (her)start (dSS heeft de ds485-bus nog niet herscand) -> foute
                    # begin-'aan' (René). Laat _device_on_states hier bewust ONGEZET; ook als
                    # dit device een ingang heeft: fetch_joker_actuator_states() leest de
                    # echte relais-stand LIVE via get_device_state() (/json/device/getState
                    # -> isOn) in het aparte OUTPUT-slot. Alleen een pure ingang/wandknop
                    # zonder output valt terug op isOn.
                    if om > 0:
                        pass
                    elif not bi:
                        self._device_on_states[dsuid] = dev_info.get("is_on", False) or False

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
                    # Free: only default presets. Pro: all zone scenes.
                    probe_scenes = ALL_ZONE_SCENES if self.pro_enabled else [SCENE_OFF, SCENE_1, SCENE_2, SCENE_3, SCENE_4]
                    for scene_nr in probe_scenes:
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
        Also polls binary input states for contact/sensor devices.
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
                        is_on = self.zone_on_after_scene(zone_id, group, scene)
                        self.set_zone_state(zone_id, group, scene=scene, is_on=is_on)
                except Exception as err:
                    _LOGGER.debug(
                        "Initial state fetch failed zone %d group %d: %s",
                        zone_id, group, err,
                    )

        # Poll binary input states for all Joker sensor devices
        await self.poll_binary_input_states()

        # Seed de echte output-stand van elke Joker-ACTOR LIVE (na de bulk-poll, zodat de
        # live-waarde de stale cache-waarde overschrijft bij (her)start). René 18 aug 2026.
        # confirm_startup=True: een 'false'-seed bij boot wordt na een settle-delay nog één
        # keer bevestigd (getState + getOutputValue), tegen de pre-settle boot-'false' die
        # René's SW-KL fout op UIT zette (22 aug 2026).
        await self.fetch_joker_actuator_states(confirm_startup=True)

        # Seed SW-UMR200 ventilation output levels so the entities have a value
        # immediately (getOutputValue per output offset — the direct relay read).
        await self.fetch_ventilation_outputs()

        # Fetch all dSS /usr/states in one call: fire/rain/alarm + day-night/holiday +
        # motion per zone + malfunction/service. Plus weather-service outdoor + sun.
        await self.fetch_dss_states()
        await self.fetch_outdoor_weather()

        # Poll presence (Present/Absent/...) at startup — events don't fire on (re)start.
        await self.fetch_apartment_state()

    async def fetch_joker_actuator_states(self, confirm_startup: bool = False) -> None:
        """Eenmalige LIVE uitlezing van de echte output-stand van elke Joker-ACTOR.

        getStructure()/getDevices() geven een gecachte "on"/"isOn" die stale kan zijn
        vlak na (her)start (dSS heeft de ds485-bus nog niet herscand). getState
        (/json/device/getState) vraagt het device direct op en is betrouwbaar voor de
        output-stand -> gebruik het hier één keer i.p.v. de bulk-cache voor de allereerste
        waarde (René, 18 aug 2026). getState.isOn = de RELAIS-output; een eventuele binaire
        ingang van hetzelfde device staat los (apart INPUT-slot), dus ook actoren MÉT ingang
        (bv. SW-KL200 e-radiator) worden hier geseed — dat is precies wat na herstart fout
        stond (René, 21 aug 2026).

        SETTLE-BEVESTIGING (René, 22 aug 2026). René bewees met getState in de browser dat
        een fysiek AAN-staande SW-KL wel degelijk 'isOn:true' geeft — getState is dus de
        JUISTE bron. Maar de allereerste seed vlak ná (her)start las voor exact dezelfde
        unit 'isOn:false' (log 16:31:19, de old_on-is-None-tak), terwijl dezelfde getState
        even later 'true' gaf. Oorzaak: bij boot heeft de dSS de ds485-bus nog niet
        herscand, dus geeft getState een pre-settle 'false'. Fix: bij ``confirm_startup``
        een 'false'-seed NIET meteen vastzetten, maar na een korte settle-delay één keer
        her-lezen én kruis-checken tegen getOutputValue (de directe relais-uitlezing,
        onafhankelijk van isOn). Een echte 'true' blijft direct staan; alleen de dubieuze
        'false' wordt bevestigd. De 30s-hoofdpoll blijft het uiteindelijke vangnet.
        """
        seen: set[str] = set()
        # Ventilatie-UMR200-uitgangen rusten op ~5% (raw ~13). getState.isOn geeft
        # voor élk niveau >0 'true', dus de Joker-switch zou bij dat rustniveau AAN
        # tonen terwijl de ventilatiestatus-sensor (10%-drempel) correct 'Niet actief'
        # toont — precies de "verkeerde beginwaarde na herstart" die René meldde
        # (SEED-DIAG beta40, 28 aug 2026: raw=13 pct=5% running=False; joker on_state=true).
        # Voor deze uitgangen geldt: output op/onder de ventilatiedrempel = fysiek UIT,
        # zodat switch én sensor met het relais overeenkomen. Commando's blijven gelijk.
        vent_dsuids = {d.get("dsuid") for d in self.get_umr200_devices() if d.get("dsuid")}

        def _vent_output_is_off(raw: int) -> bool:
            """True als een ventilatie-uitgang op/onder de drempel (rust) staat."""
            if raw < 0:
                return False
            pct = round(max(0, min(255, raw)) / 255 * 100)
            return pct <= VENTILATION_ON_THRESHOLD_PCT

        # (zone_id, dsuid, dev) waarvan de eerste seed 'false' was en die na settle
        # opnieuw gecheckt moeten worden — alleen relevant bij (her)start.
        pending_confirm: list[tuple[int, str, dict]] = []
        for zone_id in list(self.zones):
            for dev in self.get_joker_actuators_in_zone(zone_id):
                dsuid = dev.get("dsuid")
                if not dsuid or dsuid in seen:
                    continue
                seen.add(dsuid)
                try:
                    is_on = await self.api.get_device_state(dsuid)
                    old_on = self._device_on_states.get(dsuid)
                    # Eerste seed + 'false' = dubieus vlak na boot (pre-settle). Niet meteen
                    # vastzetten; even laten settelen en dan bevestigen (zie hieronder).
                    if confirm_startup and old_on is None and not is_on:
                        pending_confirm.append((zone_id, dsuid, dev))
                        continue

                    # RUNTIME relais-bevestiging (René, 23 aug 2026, beta18). René bewees dat
                    # getState.isOn tijdens BEDRIJF spontaan naar 'true' springt terwijl de
                    # SW-KL fysiek UIT is — ook de rauwe getState in de browser gaf isOn:true.
                    # isOn is dus geen betrouwbare runtime-bron voor deze unit. De directe
                    # relais-output (getOutputValue, 0..255) IS de fysieke stand; die vertrouwen
                    # we al in de settle-tak (out_val>0 redt een valse boot-'false'). Symmetrisch:
                    # claimt isOn 'true' maar geeft getOutputValue exact 0, dan staat het relais
                    # fysiek UIT en corrigeren we naar False. Alleen een expliciete 0 corrigeert;
                    # een mislezing (-1) of een echte >0 laat isOn ongemoeid. De seed/startup-tak
                    # (old_on is None) blijft onveranderd.
                    resolved = is_on
                    # BEWUST GEEN her-bewapening op een kale isOn=false (René, 28 aug 2026,
                    # beta34). Een divergente Joker-actor die fysiek UIT blijft laat isOn
                    # herhaald false->true->false flip-floppen; her-bewapenen op elke 'false'
                    # gaf dan bij elke volgende 'true' opnieuw een WARNING -> log-flood +
                    # terugkerende HA-errorbanner (precies wat de edge-trigger wilde vermijden).
                    # We her-bewapenen daarom UITSLUITEND na een bevestigd fysiek-AAN
                    # (getOutputValue>0, zie onder): pas dan is de episode echt voorbij.
                    if not confirm_startup and old_on is not None and is_on:
                        run_out_val = -1
                        try:
                            run_out_val = await self.api.get_device_output_value(dsuid)
                        except Exception as err:
                            _LOGGER.debug(
                                "Joker-actor runtime getOutputValue faalde %s: %s", dsuid, err
                            )
                        vent_rest = dsuid in vent_dsuids and _vent_output_is_off(run_out_val)
                        if run_out_val == 0 or vent_rest:
                            resolved = False
                            # Edge-triggered: één WARNING per divergentie-episode. Een
                            # blijvende isOn-leugen corrigeren we elke poll (goed), maar
                            # her-loggen op WARNING zou HA's error-banner laten terugkeren.
                            # Zolang de episode duurt → debug; nieuwe episode → weer WARNING.
                            if dsuid not in self._joker_divergence_warned:
                                self._joker_divergence_warned.add(dsuid)
                                if vent_rest:
                                    _LOGGER.warning(
                                        "[DS-DEBUG] Ventilatie-actor %s (%s) DIVERGENTIE: getState.isOn=true "
                                        "maar getOutputValue=%s op/onder %d%%-rustdrempel (fysiek UIT) "
                                        "-> gecorrigeerd naar UIT (gelijk aan ventilatiestatus-sensor)",
                                        dsuid, dev.get("name", ""), run_out_val,
                                        VENTILATION_ON_THRESHOLD_PCT,
                                    )
                                else:
                                    _LOGGER.warning(
                                        "[DS-DEBUG] Joker-actor %s (%s) DIVERGENTIE: getState.isOn=true "
                                        "maar getOutputValue=0 (relais fysiek UIT) -> gecorrigeerd naar UIT",
                                        dsuid, dev.get("name", ""),
                                    )
                            else:
                                _LOGGER.debug(
                                    "[DS-DEBUG] Joker-actor %s (%s) DIVERGENTIE houdt aan "
                                    "(isOn=true, outputValue=0) -> blijft gecorrigeerd naar UIT",
                                    dsuid, dev.get("name", ""),
                                )
                        else:
                            # Actor klopt weer (out>0): episode voorbij, WARNING her-bewapenen.
                            self._joker_divergence_warned.discard(dsuid)
                            _LOGGER.debug(
                                "[DS-DEBUG] Joker-actor %s runtime: getState=%s outputValue=%s (akkoord)",
                                dsuid, is_on, run_out_val,
                            )

                    self._device_on_states[dsuid] = resolved
                    if old_on is None:
                        # Diagnostiek (René, 22 aug 2026, beta16). René meldde een actor die
                        # fysiek UIT staat maar getState.isOn=true geeft (ook in de browser) —
                        # het spiegelbeeld van de pre-settle 'false'. Om te kunnen beslissen
                        # welke bron klopt lezen we bij de allereerste seed ook de rauwe
                        # relais-output (getOutputValue, 0..255) uit en loggen we beide naast
                        # elkaar. GEEN gedragswijziging: de seed blijft getState.isOn; dit is
                        # puur een meetregel zodat we isOn tegen de echte relais-output kunnen
                        # ijken (zoals de settle-tak dat voor de 'false' al doet).
                        seed_out_val = -1
                        try:
                            seed_out_val = await self.api.get_device_output_value(dsuid)
                        except Exception as err:
                            _LOGGER.debug(
                                "Joker-actor seed getOutputValue faalde %s: %s", dsuid, err
                            )
                        _LOGGER.debug(
                            "[DS-DEBUG] Joker-actor %s live output-stand: getState=%s "
                            "outputValue=%s (seed=getState)",
                            dsuid, is_on, seed_out_val,
                        )
                        # Ventilatie-uitgang op rustniveau (raw ~13 = 5%): getState.isOn
                        # geeft 'true', maar fysiek staat de ventilatie UIT. Seed de switch
                        # meteen als UIT zodat hij ná herstart niet ten onrechte AAN toont
                        # (de "verkeerde beginwaarde" die René meldde). SEED-DIAG beta40.
                        if is_on and dsuid in vent_dsuids and _vent_output_is_off(seed_out_val):
                            resolved = False
                            self._device_on_states[dsuid] = False
                            _LOGGER.info(
                                "Ventilatie-UMR200 %s (%s): getState.isOn=true maar output raw=%s "
                                "op/onder %d%%-rustdrempel -> switch geseed als UIT (gelijk aan "
                                "ventilatiestatus-sensor)",
                                dsuid[:12], dev.get("name", ""), seed_out_val,
                                VENTILATION_ON_THRESHOLD_PCT,
                            )
                    elif old_on != resolved:
                        # Externe wijziging die geen callScene-event opleverde (of gemist
                        # tijdens een event-loop reconnect): de 30s live getState-refresh
                        # vangt 'm alsnog op.
                        _LOGGER.info(
                            "Joker-actor output CHANGED (extern, live getState): %s (%s) on=%s (was %s)",
                            dsuid[:12], dev.get("name", ""), resolved, old_on,
                        )
                except Exception as err:
                    _LOGGER.debug("Joker-actor live state fetch faalde %s: %s", dsuid, err)

        if not pending_confirm:
            return

        # Laat de dSS de ds485-bus even herscannen en her-lees dan de dubieuze 'false's.
        await asyncio.sleep(JOKER_STARTUP_SETTLE_SECONDS)
        for zone_id, dsuid, dev in pending_confirm:
            is_on = False
            out_val = -1
            try:
                is_on = await self.api.get_device_state(dsuid)
            except Exception as err:
                _LOGGER.debug("Joker-actor settle getState faalde %s: %s", dsuid, err)
            # Onafhankelijke kruis-check: de rauwe relais-output (0..255). >0 = relais AAN,
            # ook als getState.isOn nog 'false' teruggeeft. Rescue-t een valse boot-'false'.
            try:
                out_val = await self.api.get_device_output_value(dsuid)
            except Exception as err:
                _LOGGER.debug("Joker-actor settle getOutputValue faalde %s: %s", dsuid, err)
            resolved = bool(is_on) or (out_val > 0)
            self._device_on_states[dsuid] = resolved
            _LOGGER.debug(
                "[DS-DEBUG] Joker-actor %s live output-stand (na settle): getState=%s "
                "outputValue=%s -> %s",
                dsuid, is_on, out_val, resolved,
            )

    async def poll_binary_input_states(self) -> None:
        """Poll all device runtime info via the apartment/getDevices web API.

        Single HTTP call → updates binary input state (1=active, 2=inactive)
        AND the per-device ``on`` output state for every device. No dS-bus
        traffic because the dSS serves cached state.
        """
        try:
            devices = await self.api.get_all_devices_full()
        except Exception as err:
            _LOGGER.debug("Device poll failed: %s", err)
            return

        # NB: per-device power/energy is NOT read here — getDevices only returns a stale
        # cache (often 0 W). Live values come from _power_poll_loop (getSensorValue2).

        # Parse binary inputs (1=active, 2=inactive)
        all_states: dict[str, int] = {}
        for dev in devices:
            dsuid = dev.get("dSUID", "")
            if not dsuid:
                continue
            bi = dev.get("binaryInputs", [])
            if bi and "state" in bi[0]:
                all_states[dsuid] = bi[0]["state"]
            # Cache runtime output info for every device
            self._device_runtime[dsuid] = {
                "on": bool(dev.get("on", False)),
                "is_present": bool(dev.get("isPresent", True)),
                "is_valid": bool(dev.get("isValid", True)),
                "output_mode": int(dev.get("outputMode", 0) or 0),
            }

            # LET OP: de OUTPUT-stand van een Joker-ACTOR (de switch) wordt hier
            # BEWUST NIET (meer) uit dev["on"] gezet. getDevices levert een gecachte
            # "on" die stale is (de dSS herscant de ds485-bus niet per poll) — precies
            # daarom seeden we bij (her)start de switch al LIVE via getState
            # (fetch_joker_actuator_states). Deze fast-poll (elke 5s) overschreef die
            # live-waarde daarna weer met de stale cache → switch klapte "na enige tijd"
            # terug naar fout (René, SW-KL200 e-radiator, 22 aug 2026). De OUTPUT-stand
            # komt nu uit: (1) live getState bij startup, (2) callScene-events, en
            # (3) een live getState-refresh in de 30s-hoofdpoll (fetch_joker_actuator_states).
            # Deze snelle poll blijft alleen voor de BINAIRE INGANG (hieronder).

        # Log poll results for debugging (every poll cycle at debug level)
        binary_devices = {d: dev for d, dev in self.devices.items() if dev.get("binary_inputs")}
        if binary_devices:
            _LOGGER.debug(
                "Binary poll: %d devices with binary inputs, %d states returned from API",
                len(binary_devices), len(all_states),
            )

        for dsuid, dev in self.devices.items():
            if not dev.get("binary_inputs"):
                continue
            bi_state = all_states.get(dsuid)
            if bi_state is None:
                _LOGGER.debug(
                    "Binary poll: no state for %s (%s) — dsuid not in API response. "
                    "Known API dsuids: %s",
                    dsuid[:12], dev.get("name", ""),
                    list(all_states.keys())[:5] if not all_states.get(dsuid) else "matched",
                )
                continue
            # dSS binary input: 1=active, 2=inactive → INPUT-slot (leest de binary_sensor)
            is_active = (bi_state == 1)
            old_state = self._device_input_states.get(dsuid)
            self._device_input_states[dsuid] = is_active
            if old_state != is_active:
                _LOGGER.info(
                    "Binary input CHANGED: %s (%s) state=%d active=%s (was %s)",
                    dsuid[:12], dev.get("name", ""),
                    bi_state, is_active, old_state,
                )

    async def fetch_climate_data(self, skip_temp_prefetch: bool = False) -> None:
        """Fetch climate control status and config for zones. PRO.

        Tries all zones — not just those with GROUP_HEATING/GROUP_TEMP_CONTROL,
        because some setups (PLAN44, EnOcean, external actuators) have climate
        control configured at the zone level without heating-group devices.
        Also pre-fetches temperature values so the fallback in has_temp_control
        works at startup even when ControlMode is 0 (cooling mode).

        skip_temp_prefetch: when True, skip the getTemperatureControlValues
        pre-fetch because the caller already fetched it this cycle (the main
        poll _async_update_data does so before calling us). Removes a duplicate
        apartment-wide dSS call per poll cycle (René, 25 aug 2026).
        """
        if not self.pro_enabled:
            return

        # Pre-fetch temperature values — needed as fallback when in cooling mode
        # (getTemperatureControlConfig2 may return ControlMode=0 while cooling is active)
        if not skip_temp_prefetch:
            try:
                temp_data = await self.api.get_temperature_values()
                for zone_data in temp_data:
                    zone_id = zone_data.get("id")
                    if zone_id is not None and zone_id > 0:
                        existing = self._temperatures.get(zone_id, {})
                        existing.update(zone_data)
                        self._temperatures[zone_id] = existing
            except Exception as err:
                _LOGGER.debug("Pre-fetch temperature values failed: %s", err)

        for zone_id, zone_info in self.zones.items():
            # Fetch config once per zone: zones met bevestigde klimaatregeling
            # zitten in _climate_config, zones die bevestigd GEEN regeling
            # hebben in _climate_config_checked. Beide worden overgeslagen, zodat
            # we niet elke vangnet-cyclus opnieuw getTemperatureControlConfig2
            # aanroepen voor zones waarvan het antwoord al bekend is.
            if (
                zone_id not in self._climate_config
                and zone_id not in self._climate_config_checked
            ):
                try:
                    config = await self.api.get_temperature_control_config(zone_id)
                    _LOGGER.info(
                        "Zone %d (%s) climate config: %s",
                        zone_id, zone_info["name"], config,
                    )
                    # Any non-empty config response = climate control present
                    # ControlMode can be int (0=off, >0=active) or string ("control")
                    control_mode = config.get("ControlMode", config.get("mode", ""))
                    if _is_climate_control_active(control_mode):
                        self._climate_config[zone_id] = config
                    else:
                        # Succesvolle call, maar geen actieve klimaatregeling:
                        # onthoud dit zodat we deze zone niet elke cyclus opnieuw
                        # bevragen. Alleen bij een geslaagde call (niet in de
                        # except-tak), zodat een tijdelijke dSS-fout retrybaar
                        # blijft.
                        self._climate_config_checked.add(zone_id)
                except DigitalStromApiError as err:
                    _LOGGER.debug(
                        "Zone %d (%s) no climate config: %s",
                        zone_id, zone_info["name"], err,
                    )
            # Only fetch status if zone has confirmed temp control
            if not self.has_temp_control(zone_id):
                _LOGGER.debug(
                    "Zone %d (%s) SKIP temp-control status: no temp_control "
                    "(config=%s groups=%s temps=%s)",
                    zone_id, zone_info["name"],
                    self._climate_config.get(zone_id),
                    self.zones.get(zone_id, {}).get("groups"),
                    self._temperatures.get(zone_id),
                )
                continue
            try:
                status = await self.api.get_temperature_control_status(zone_id)
                self._climate_status[zone_id] = status
                _LOGGER.debug(
                    "Zone %d (%s) temp-control status: %s", zone_id,
                    zone_info["name"], status,
                )
            except DigitalStromApiError:
                pass

        # Always poll heating_system_mode from the API each cycle.
        # stateChange events don't reliably fire for all mode transitions (e.g. cooling→heating),
        # so we re-read every fetch_climate_data() call to stay in sync.
        try:
            raw = await self.api.get_user_defined_states()
            for entry in raw:
                if entry.get("name") == "heating_system_mode":
                    state_val = str(entry.get("state", "")).lower()
                    value_val = entry.get("value")
                    new_cooling = (
                        state_val in ("inactive", "off", "cooling", "2") or value_val == 2
                    )
                    if new_cooling != self._heating_system_cooling:
                        self._heating_system_cooling = new_cooling
                        _LOGGER.info(
                            "heating_system_mode changed (polled): state=%s value=%s → cooling=%s",
                            state_val, value_val, self._heating_system_cooling,
                        )
                        self.async_update_listeners()
                    elif not self._heating_mode_initialized:
                        self._heating_system_cooling = new_cooling
                        _LOGGER.info(
                            "heating_system_mode initialized: state=%s value=%s → cooling=%s",
                            state_val, value_val, self._heating_system_cooling,
                        )
                    self._heating_mode_initialized = True
                    break
        except Exception as err:
            _LOGGER.debug("Could not fetch heating_system_mode: %s", err)

    async def fetch_sensor_data(self) -> dict | None:
        """Fetch apartment-wide sensor values (outdoor, per-zone). PRO.

        Returns the raw getSensorValues response so the caller can hand it to
        fetch_outdoor_weather and avoid a second identical apartment-wide call
        in the same poll cycle (René, 25 aug 2026)."""
        if not self.pro_enabled:
            return None
        try:
            data = await self.api.get_sensor_values()
            self._outdoor_sensors = data.get("outdoor", {})
            for zone_data in data.get("zones", []):
                zid = zone_data.get("id")
                if zid:
                    self._zone_sensors[zid] = zone_data
            # Mark this cycle's apartment cache as fresh. The actual per-device
            # mapping is done once, by fetch_device_sensors() which runs right
            # after this in the poll cycle — no double mapping (René, 26 aug 2026).
            self._zone_sensors_fresh = True
            return data
        except DigitalStromApiError:
            return None

    async def fetch_circuit_data(self) -> None:
        """Fetch dSM circuit/meter information, per-circuit power and energy.

        Power: instantaneous Watts per dSM (via metering/getLatest).
        Energy: lifetime cumulative Watt-seconds per dSM (via circuit/getEnergyMeterValue).
        The energy values feed the HA Energy Dashboard via TOTAL_INCREASING sensors.
        """
        try:
            if not self._circuits:
                all_circuits = await self.api.get_circuits()
                # Diagnose-hulp: alle circuits + hwName + dSUID (DEBUG).
                _LOGGER.debug(
                    "Alle circuits van de dSS (%d): %s",
                    len(all_circuits),
                    " | ".join(f"{c.get('name','?')} [hw={c.get('hwName','?')}] dsuid={(c.get('dSUID','') or '')[:18]}"
                               for c in all_circuits),
                )
                # dSM20/dSM25 meten. dSM11 is EOL -> overslaan. dSM12 is wel ondersteund en
                # levert via metering/getLatest geldige W en Wh (geverifieerd op een
                # dSM12-only installatie) -> niet langer uitgesloten. De dSM-energie-corruptie
                # die hier eerder speelde kwam van getSensorValue2-bus-starvation, die nu
                # apart is opgelost (per-device power = events-only); dSM12-metering is veilig.
                self._circuits = [
                    c for c in all_circuits
                    if c.get("hwName", "").startswith("dSM")
                    and not c.get("hwName", "").startswith("dSM11")
                ]
                _LOGGER.info(
                    "Gemeten dSM-meters (na filter): %d — %s",
                    len(self._circuits),
                    ", ".join(f"{c.get('name','')} [{c.get('hwName','')}]" for c in self._circuits) or "(geen)",
                )
            # Fetch power + cumulative energy voor ALLE meters in 2 calls i.p.v.
            # 2 per circuit. metering/getLatest met from=.meters(all) geeft één
            # value-entry per meter terug, elk getagd met zijn eigen dSUID én dsid.
            # Geverifieerd tegen een echte dSS-respons: het dSUID-veld in de entry
            # is exact gelijk aan circuit["dSUID"] (bv. ...0000003c900), dus we
            # koppelen 1-op-1 zonder te gokken. type=energy (Wh) blijft een aparte
            # call — power en energie kunnen niet in één respons.
            def _index_by_id(values: list[dict] | None) -> dict[str, dict]:
                idx: dict[str, dict] = {}
                for v in values or []:
                    for key in (v.get("dSUID"), v.get("dsid")):
                        if key:
                            idx[key] = v
                return idx

            p_all = e_all = None
            try:
                p_all = await self.api.get_metering_latest(meter_dsuid=".meters(all)")
            except DigitalStromApiError:
                pass
            try:
                # Genormaliseerde metering-API (Wh) — getEnergyMeterValue gaf een raw
                # waarde met model-afhankelijke eenheid. metering type=energy = consistent.
                e_all = await self.api.get_metering_latest(
                    meter_dsuid=".meters(all)", meter_type="energy"
                )
            except DigitalStromApiError:
                pass
            p_idx = _index_by_id(p_all)
            e_idx = _index_by_id(e_all)

            for circuit in self._circuits:
                dsuid = circuit.get("dSUID", "")
                hw = circuit.get("hwName", "")
                if not dsuid:
                    continue
                pv = p_idx.get(dsuid)
                ev = e_idx.get(dsuid)
                # Vangnet: zit een meter niet in de bulk-respons, haal hem gericht
                # per-dSM op. Zo verliezen we nooit stilletjes een Energie-sensor —
                # in het normale geval blijft het bij 2 calls per cyclus.
                if pv is None:
                    try:
                        r = await self.api.get_metering_latest(
                            meter_dsuid=f".meters({dsuid})"
                        )
                        pv = r[0] if r else None
                    except DigitalStromApiError:
                        pv = None
                if ev is None:
                    try:
                        r = await self.api.get_metering_latest(
                            meter_dsuid=f".meters({dsuid})", meter_type="energy"
                        )
                        ev = r[0] if r else None
                    except DigitalStromApiError:
                        ev = None
                if pv is not None:
                    self._circuit_power[dsuid] = int(pv.get("value", 0))
                if ev is not None:
                    wh = ev.get("value")
                    if wh and wh > 0:
                        self._circuit_energy_wh[dsuid] = int(wh)
                # Diagnose-hulp: gekoppelde metering-entry per dSM (DEBUG).
                _LOGGER.debug(
                    "dSM-meter %s [%s] dsuid=%s → power=%s | energy=%s",
                    circuit.get("name", ""), hw, dsuid, pv, ev,
                )
        except DigitalStromApiError as err:
            _LOGGER.debug("Circuit data fetch failed: %s", err)

    # =====================================================================
    # User Defined Actions & States
    # =====================================================================

    async def fetch_user_actions(self) -> None:
        """Fetch User Defined Actions from dSS — buttons in HA."""
        try:
            raw = await self.api.get_user_defined_actions()
        except DigitalStromApiError as err:
            _LOGGER.debug("User action fetch failed: %s", err)
            return
        # Keep only true User Defined Actions (created via Configurator addon)
        # and skip disabled entries
        filtered = [
            a for a in raw
            if a.get("source") == USER_ACTION_SOURCE
            and not a.get("disabled", False)
            and a.get("id")
            and a.get("name")
        ]
        # De-duplicate by id (keep first occurrence)
        seen: set[str] = set()
        unique: list[dict] = []
        for a in filtered:
            if a["id"] in seen:
                continue
            seen.add(a["id"])
            unique.append(a)
        self._user_actions = unique
        _LOGGER.info(
            "User defined actions: %d (of %d total events)",
            len(unique), len(raw),
        )

    async def fetch_timed_events(self) -> None:
        """Fetch dSS Timed Events (Configurator timers / klokken)."""
        try:
            entries = await self.api.get_timed_events()
        except DigitalStromApiError as err:
            _LOGGER.debug("Timed events fetch failed: %s", err)
            return
        self._timed_events = {e["id"]: e for e in entries}
        _LOGGER.info(
            "Configurator timers: %d imported",
            len(self._timed_events),
        )

    async def fetch_custom_states(self) -> None:
        """Fetch User Defined States created in the dSS Configurator.

        These are the entries shown under *Activities > User Defined States*
        in the Configurator. Their definitions (display name, set/reset
        labels) live in a script subtree; their current value comes from the
        addon-states subtree. We join them on the state id.
        """
        try:
            definitions = await self.api.get_custom_state_definitions()
        except DigitalStromApiError as err:
            _LOGGER.debug("Custom state definitions fetch failed: %s", err)
            return
        try:
            states = await self.api.get_addon_states(
                "system-addon-user-defined-states"
            )
        except DigitalStromApiError as err:
            _LOGGER.debug("Addon states fetch failed: %s", err)
            states = {}
        merged: dict[str, dict] = {}
        by_category: dict[str, int] = {}
        for d in definitions:
            sid = d["id"]
            lookup_key = d.get("lookup_key", sid)
            # Remember WHICH runtime key actually matched: that key is the name
            # the dSS itself registered the state under in /usr/addon-states, and
            # is therefore the authoritative name for a /json/state/set write.
            if lookup_key in states:
                runtime, runtime_name = states[lookup_key], lookup_key
            elif sid in states:
                runtime, runtime_name = states[sid], sid
            else:
                runtime, runtime_name = {}, None
            merged[sid] = {
                "id": sid,
                "name": d["name"] or f"State {sid}",
                "set_name": d["set_name"],
                "reset_name": d["reset_name"],
                "state": runtime.get("state", ""),
                "value": runtime.get("value"),
                "category": d.get("category", "custom-states"),
                "lookup_key": lookup_key,
                "runtime_name": runtime_name,
                "active_value": d.get("active_value"),
                "inactive_value": d.get("inactive_value"),
            }
            by_category[d.get("category", "?")] = by_category.get(d.get("category", "?"), 0) + 1
        self._custom_states = merged
        _LOGGER.info(
            "Configurator User Defined States: %d imported (%s)",
            len(merged),
            ", ".join(f"{c}={n}" for c, n in by_category.items()),
        )

    async def fetch_user_states(self) -> None:
        """Fetch User Defined / apartment-wide states from dSS — sensors in HA.

        System states that are already exposed via dedicated entities
        (rain, alarms, presence, etc.) are skipped — see SKIP_USER_STATES.
        """
        try:
            raw = await self.api.get_user_defined_states()
        except DigitalStromApiError as err:
            _LOGGER.debug("User state fetch failed: %s", err)
            return
        for entry in raw:
            name = entry.get("name", "")
            if not name or name in SKIP_USER_STATES:
                continue
            self._user_states[name] = {
                "state": entry.get("state", ""),
                "value": entry.get("value"),
            }
        _LOGGER.info(
            "User defined states: %d imported (of %d total)",
            len(self._user_states), len(raw),
        )

    # Zone-level sensor keys (pre-scaled by the dSS) → HA sensor type.
    _ZONE_SENSOR_KEY_MAP = {
        "TemperatureValue": SENSOR_TEMPERATURE,
        "HumidityValue": SENSOR_HUMIDITY,
        "CO2concentrationValue": SENSOR_CO2,
        "BrightnessValue": SENSOR_BRIGHTNESS,
    }

    @staticmethod
    def _zone_sensor_entries(zone_data: dict) -> list[dict]:
        """Named-key sensor entries for one zone, tolerant of both dSS shapes.

        Both /json/zone/getSensorValues and the per-zone blocks of
        /json/apartment/getSensorValues expose their readings as a "values"
        list of {SensorNameValue: x} dicts. If a caller hands us a flat dict
        (a zone block without a "values" list), we wrap it so the exact same
        extraction works either way — no assumption about which shape it is."""
        if not isinstance(zone_data, dict):
            return []
        values = zone_data.get("values")
        if isinstance(values, list):
            return values
        return [zone_data]

    def _map_zone_sensor_data(self, zone_id: int, zone_info: dict, zone_data: dict) -> int:
        """Map one zone's pre-scaled readings onto the zone's devices.

        Returns the number of values applied."""
        found = 0
        for entry in self._zone_sensor_entries(zone_data):
            if not isinstance(entry, dict):
                continue
            for key, stype in self._ZONE_SENSOR_KEY_MAP.items():
                if key not in entry:
                    continue
                try:
                    val = round(float(entry[key]), 2)
                except (TypeError, ValueError):
                    continue
                # First device in this zone that has this sensor type.
                dsuid = self._find_device_with_sensor(zone_info, stype)
                if dsuid:
                    self._device_sensor_values.setdefault(dsuid, {})[stype] = val
                    found += 1
        return found

    def map_zone_sensors_to_devices(self) -> None:
        """PRO: derive per-device temp/humidity/CO2/brightness from the
        apartment getSensorValues already fetched this cycle (self._zone_sensors).

        This is the exact same data the FREE per-zone loop would gather, so for
        PRO installs it lets us skip the extra get_zone_sensor_values call per
        zone every cycle — that apartment-wide call runs anyway for the outdoor/
        climate read (René, 26 aug 2026)."""
        found_count = 0
        for zone_id, zone_info in self.zones.items():
            zone_data = self._zone_sensors.get(zone_id)
            if zone_data:
                found_count += self._map_zone_sensor_data(zone_id, zone_info, zone_data)
        _LOGGER.debug("Mapped %d device sensor values from apartment cache", found_count)

    async def fetch_device_sensors(self) -> None:
        """Fetch device sensor values (Ulux, thermostats, etc.), zone-level.

        The dSS pre-scales all values — no manual bus-encoding needed.
        After startup, real-time updates come via deviceSensorValue events
        (sensorValueFloat, also pre-scaled).

        PRO: reuse the apartment-wide getSensorValues that fetch_sensor_data()
        fetched EARLIER THIS SAME cycle (self._zone_sensors) and map it once —
        no per-zone get_zone_sensor_values calls. The freshness flag guards
        against two things René flagged (26 aug 2026): (1) it maps only the
        current cycle's data, so PRO no longer maps last cycle's stale cache
        here and then remaps fresh in fetch_sensor_data — one mapping per cycle;
        (2) if the apartment fetch structurally failed this cycle (network
        hiccup, licence expiring mid-run) the flag stays False, so we fall back
        to the per-zone vangnet loop instead of silently reusing an ageing
        cache. FREE: the per-zone loop is the only option (get_zone_sensor_values
        is license-free; get_sensor_values is PRO-only), so it always runs for
        free installs."""
        if self.pro_enabled and self._zone_sensors_fresh:
            self.map_zone_sensors_to_devices()
            return

        found_count = 0
        for zone_id, zone_info in self.zones.items():
            try:
                data = await self.api.get_zone_sensor_values(zone_id)
            except (DigitalStromApiError, DigitalStromAuthError):
                continue
            found_count += self._map_zone_sensor_data(zone_id, zone_info, data)

        _LOGGER.debug("Polled %d sensor values from zone API", found_count)
        # Power/energy polling runs in _power_poll_loop (background task) — not here.
        # Polling here would block the DataUpdateCoordinator refresh on large installations.

    async def _poll_device_power_sensors(self, energy: bool = False) -> None:
        """Per-device getSensorValue2 polling — UITGESCHAKELD (v3.3.22).

        Op grote installaties veroorzaakte asyncio.gather() honderden parallelle
        requests naar de dSS. SW-series apparaten ondersteunen getSensorValue2 niet
        → 403 Forbidden flood → dSS overbelast en onbereikbaar.

        Per-device waarden worden nu uitsluitend via deviceSensorValue events
        bijgewerkt (event-driven, dSS pusht zelf). Zone-/circuit-level energie
        via fetch_circuit_data() werkt gewoon door.
        """
        _LOGGER.debug("Per-device power poll skipped (disabled in v3.3.22)")

    async def _power_poll_loop(self) -> None:
        """Per-device power polling is DISABLED — events only (deviceSensorValue).

        getSensorValue2 is an expensive SERIAL s485-bus read (~1.4s each). Polling it
        STARVES the dSS metering controller (dSS-log: "Metering pollLoop exceeded 1s
        budget" + "deltaEnergy: too long delay → setting new baseline"), wat de dSM-energie
        op nieuwere meters (dSM20/25) corrupt maakt. Per-device vermogen komt daarom nu
        UITSLUITEND uit de dSS-eigen deviceSensorValue-events; de dSM-meters leveren het
        per-circuit vermogen/energie. Zo vechten de twee niet om de bus."""
        _LOGGER.info("Per-device power: events-only (geen getSensorValue2-polling, bus vrij voor metering)")
        return

    async def fetch_device_power_sensors(self) -> None:
        """Fast startup seed from structure data only — NO live getSensorValue2 calls.

        getSensorValue2 is an expensive s485-bus read (~1.4s each); doing a live round for
        all metering devices here BLOCKED setup for minutes on large installs. Live values
        come from _power_poll_loop in the background (rotating, gentle)."""
        seeded = 0
        for dsuid, dev in self.devices.items():
            for sensor in dev.get("sensors", []):
                stype = sensor.get("type")
                if stype not in (SENSOR_ACTIVE_POWER, SENSOR_ACTIVE_ENERGY):
                    continue
                val = sensor.get("value")
                if val is not None:
                    try:
                        self._device_sensor_values.setdefault(dsuid, {})[stype] = round(float(val), 2)
                        seeded += 1
                    except (TypeError, ValueError):
                        pass
        _LOGGER.debug("Startup power seed: %d devices from structure (no API calls)", seeded)

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
            return NAMED_SCENES_SHADE.get(scene_nr, AREA_SCENE_NAMES.get(scene_nr, f"Scene {scene_nr}"))
        if group == GROUP_HEATING:
            return GROUP_HEATING_SCENES.get(scene_nr, AREA_SCENE_NAMES.get(scene_nr, f"Scene {scene_nr}"))
        return NAMED_SCENES.get(scene_nr, AREA_SCENE_NAMES.get(scene_nr, f"Scene {scene_nr}"))

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

        Priority:
        1. Climate config from getTemperatureControlConfig2 (most reliable, but
           returns ControlMode=0 when system is in cooling mode)
        2. Zone groups from dSS structure — GROUP_TEMP_CONTROL (48) or
           GROUP_COOLING (9) always mean temperature control, regardless of mode
        3. Temperature values (TemperatureValue / NominalValue) as last resort
        """
        # Memoize: eenmaal-klimaatzone = blijft-klimaatzone. Zo blijft de per-zone
        # status (incl. ControlValue/regelwaarde) gepolld nadat de dSS naar koelen
        # schakelt (waar getTemperatureControlConfig2 ControlMode=0 teruggeeft).
        if zone_id in self._temp_control_zones:
            return True

        result = False
        # Primary: climate config present = has temp control
        if self._climate_config.get(zone_id):
            result = True
        else:
            # Reliable fallback: zone groups from dSS structure (available at
            # startup, independent of API calls that may fail in cooling mode)
            groups = self.zones.get(zone_id, {}).get("groups", set())
            if groups & {GROUP_TEMP_CONTROL, GROUP_COOLING}:
                result = True
            else:
                # Last resort: temperature values (periodic poll / pre-fetch)
                data = self._temperatures.get(zone_id)
                if data:
                    tv = data.get("TemperatureValue")
                    nv = data.get("NominalValue")
                    if (tv is not None and tv > 0) or (nv is not None and nv > 0):
                        result = True

        if result:
            self._temp_control_zones.add(zone_id)
        return result

    def get_temperature(self, zone_id: int) -> float | None:
        """Get target/nominal (setpoint) temperature for a zone.

        Polled sources, in order — so the setpoint survives the gap between
        Thanos stateChange events. Right after a heating/cooling changeover or a
        restart the apartment temp-control values briefly read 0/None; the
        per-zone status keeps working.
        1. apartment getTemperatureControlValues (NominalValue)
        2. per-zone getTemperatureControlStatus (NominalValue)
        """
        # Guard the comparison: right after a dSS restart NominalValue can be
        # present but explicitly None (dict.get only substitutes the default when
        # the key is absent). None > 0 would raise TypeError, which — raised from
        # a climate entity's async_write_ha_state inside async_update_listeners —
        # aborts the whole listener loop and leaves every entity registered after
        # it (all power/energy sensors) unavailable. Fall through to None instead.
        data = self._temperatures.get(zone_id)
        if data:
            nv = data.get("NominalValue")
            if isinstance(nv, (int, float)) and not isinstance(nv, bool) and nv > 0:
                return nv
        status = self._climate_status.get(zone_id)
        if status:
            nv = status.get("NominalValue")
            if isinstance(nv, (int, float)) and not isinstance(nv, bool) and nv > 0:
                return nv
        return None

    def _zone_device_temperature(self, zone_id: int) -> float | None:
        """Temperature from any device sensor in the zone (polled)."""
        zone_info = self.zones.get(zone_id, {})
        for dsuid in zone_info.get("devices", []):
            dev_sensors = self._device_sensor_values.get(dsuid, {})
            if SENSOR_TEMPERATURE in dev_sensors:
                return dev_sensors[SENSOR_TEMPERATURE]
        return None

    def get_current_temperature(self, zone_id: int) -> float | None:
        """Get actual measured temperature for a zone.

        Tries every polled source so the value survives the gap between Thanos
        stateChange events. After a changeover/restart the apartment temp-control
        values briefly read 0/None, but the per-zone status, the apartment sensor
        poll and the device sensors keep delivering a reading.
        """
        data = self._temperatures.get(zone_id)
        if data:
            # Prefer TemperatureValue from getTemperatureControlValues
            tv = data.get("TemperatureValue")
            if tv and tv > 0:
                return tv
            # Sensor event data
            sv = data.get("sensorValue")
            if sv and sv > 0:
                return sv
        # Per-zone getTemperatureControlStatus (polled each cycle)
        status = self._climate_status.get(zone_id)
        if status:
            tv = status.get("TemperatureValue")
            if tv and tv > 0:
                return tv
        # Apartment getSensorValues per-zone reading (polled)
        zs = self._zone_sensors.get(zone_id)
        if zs:
            tv = zs.get("TemperatureValue")
            if tv and tv > 0:
                return tv
        # Device temperature sensors in the zone (polled / events)
        return self._zone_device_temperature(zone_id)

    def get_any_temperature(self, zone_id: int) -> float | None:
        """Get any available temperature for a zone (regardless of temp control).

        Used for rooms that have a temperature sensor but no heating/temp control.
        Checks: TemperatureValue, sensorValue from events, device sensors.
        """
        # get_current_temperature now already covers temp-control data, the
        # per-zone status, the apartment sensor poll and device sensors.
        return self.get_current_temperature(zone_id)

    def get_control_value(self, zone_id: int) -> float | None:
        """Get the zone control value (signed): NEGATIEF = koelvraag,
        POSITIEF = verwarmvraag (de dSS-vloerklep-aansturing). Werkt zo ook in
        koelmodus. Bron: apartement getTemperatureControlValues eerst, anders de
        per-zone getTemperatureControlStatus (die ook gevuld is als de apartement-
        poll ControlMode=0 teruggeeft, bv. tijdens koelen)."""
        data = self._temperatures.get(zone_id)
        if data and data.get("ControlValue") is not None:
            return data["ControlValue"]
        status = self._climate_status.get(zone_id)
        if status and status.get("ControlValue") is not None:
            return status["ControlValue"]
        return None

    def get_climate_status(self, zone_id: int) -> dict | None:
        return self._climate_status.get(zone_id)

    def get_climate_config(self, zone_id: int) -> dict | None:
        return self._climate_config.get(zone_id)

    @property
    def is_cooling_mode(self) -> bool:
        """True when the heating system is in cooling mode (detected via event)."""
        return self._heating_system_cooling

    def get_zone_sensor(self, zone_id: int) -> dict:
        return self._zone_sensors.get(zone_id, {})

    def get_circuit_power(self, dsuid: str) -> int:
        return self._circuit_power.get(dsuid, 0)

    def get_circuit_energy_kwh(self, dsuid: str) -> float | None:
        """Cumulative energy for a single dSM in kWh (TOTAL_INCREASING)."""
        wh = self._circuit_energy_wh.get(dsuid)
        if wh is None or wh <= 0:
            return None
        return round(wh / 1000, 3)  # Wh → kWh

    @property
    def apartment_energy_kwh(self) -> float | None:
        """Sum of all dSM cumulative energy values, in kWh.

        Returns None until at least one meter has reported a value.
        """
        if not self._circuit_energy_wh:
            return None
        total = sum(v for v in self._circuit_energy_wh.values() if v > 0)
        if total <= 0:
            return None
        return round(total / 1000, 3)  # Wh → kWh

    @property
    def user_actions(self) -> list[dict]:
        return self._user_actions

    @property
    def user_states(self) -> dict[str, dict]:
        return self._user_states

    def get_user_state(self, name: str) -> dict | None:
        return self._user_states.get(name)

    @property
    def timed_events(self) -> dict[str, dict]:
        """Configurator timers / klokken."""
        return self._timed_events

    def get_timed_event(self, event_id: str) -> dict | None:
        return self._timed_events.get(event_id)

    async def set_timer_enabled(self, event_id: str, enabled: bool) -> None:
        """Toggle a Configurator timer on/off and update the local cache."""
        await self.api.set_timed_event_enabled(event_id, enabled)
        if event_id in self._timed_events:
            self._timed_events[event_id]["enabled"] = enabled
            self.async_update_listeners()

    async def run_timer_once(self, event_id: str) -> int:
        """Execute all configured actions of a timer immediately.

        Returns the number of actions executed. Honours per-action delay
        (in seconds). The timer's schedule and enabled state are not
        touched — this is a one-off manual fire.
        """
        actions = await self.api.get_timer_actions(event_id)
        executed = 0
        for action in actions:
            delay = action.get("delay", 0) or 0
            if delay > 0:
                await asyncio.sleep(delay)
            atype = action.get("type")
            try:
                if atype == "zone-scene":
                    await self.api.call_scene(
                        int(action.get("zone", 0)),
                        int(action.get("group", 1)),
                        int(action.get("scene", 0)),
                    )
                elif atype == "device-scene":
                    dsuid = action.get("dsuid")
                    if dsuid:
                        await self.api.device_call_scene(
                            dsuid, int(action.get("scene", 0))
                        )
                else:
                    _LOGGER.warning(
                        "Timer %s: unsupported action type '%s' — skipped",
                        event_id, atype,
                    )
                    continue
                executed += 1
            except DigitalStromApiError as err:
                _LOGGER.error(
                    "Timer %s action %s failed: %s",
                    event_id, action.get("index"), err,
                )
        return executed

    @property
    def custom_states(self) -> dict[str, dict]:
        """Configurator-defined User Defined States."""
        return self._custom_states

    def get_custom_state(self, state_id: str) -> dict | None:
        return self._custom_states.get(state_id)

    def update_custom_state_runtime(
        self, state_id: str, state: str, value: int | None,
    ) -> None:
        """Update the runtime state/value of a custom state (called from events)."""
        if state_id in self._custom_states:
            self._custom_states[state_id]["state"] = state
            self._custom_states[state_id]["value"] = value

    def _find_custom_state_by_key(self, key: str) -> str | None:
        """Return the state id whose id OR lookup_key matches the given key."""
        if key in self._custom_states:
            return key
        for sid, data in self._custom_states.items():
            if data.get("lookup_key") == key:
                return sid
        return None

    def friendly_state_name(self, state_name: str) -> str:
        """Render a human-readable name for a dSS state.

        ``dev.<dsuid>.status.<thing>`` and ``dev.<dsuid>.<thing>`` states are
        per-device states. We look up the device name from the structure and
        suffix the trailing component, e.g.
        ``dev.22cc..78271b174f00.status.playbacktype`` →
        ``Sonos Living PlaybackType``.
        """
        parts = state_name.split(".")
        if len(parts) >= 3 and parts[0] == "dev":
            dsuid = parts[1]
            dev = self.devices.get(dsuid)
            if dev and dev.get("name"):
                suffix = parts[-1].replace("_", " ").title()
                return f"{dev['name']} {suffix}"
        return state_name

    def get_device_sensor_value(self, dsuid: str, sensor_type: int) -> float | None:
        """Get a device sensor value by type."""
        return self._device_sensor_values.get(dsuid, {}).get(sensor_type)

    def zone_on_after_scene(self, zone_id: int, group: int, scene: int) -> bool:
        """Bepaal of een zone 'aan' is na een callScene, met area-besef (#26).

        DS stuurt bij het uitschakelen van één area een area-uit-scene (1-4); dat
        zet maar dat ene area uit. De vroegere logica (is_on = scene != 0) zag die
        scenes als 'aan' -> lamp bleef in HA hangen. Nu:
          - scene 0 (SCENE_OFF): hele zone uit;
          - area-aan (6-9): dat area aan -> zone aan;
          - area-uit (1-4): dat area uit -> zone uit zodra ALLE bekende areas uit
            zijn (tenzij de zone via een preset 'broadcast'-aan staat);
          - elke andere scene (presets): hele zone aan.
        Bij twijfel (area-uit terwijl niets getrackt is) valt 'aan' terug op het
        broadcast-vlag -> nooit een regressie t.o.v. het oude gedrag.
        """
        key = (zone_id, group)
        if scene == SCENE_OFF:
            self._zone_areas_on[key] = set()
            self._zone_broadcast_on[key] = False
            return False
        if scene in AREA_ON_SCENES:
            self._zone_areas_on.setdefault(key, set()).add(AREA_ON_SCENES[scene])
            return True
        if scene in AREA_OFF_SCENES:
            areas = self._zone_areas_on.setdefault(key, set())
            areas.discard(AREA_OFF_SCENES[scene])
            return bool(areas) or self._zone_broadcast_on.get(key, False)
        # Elke andere scene = hele-zone-preset -> aan
        self._zone_broadcast_on[key] = True
        return True

    def get_zone_state(self, zone_id: int, group: int) -> dict[str, Any]:
        return self._zone_states.get((zone_id, group), {"scene": None, "value": None})

    def set_zone_state(self, zone_id: int, group: int, **kwargs: Any) -> None:
        key = (zone_id, group)
        if key not in self._zone_states:
            self._zone_states[key] = {"scene": None, "value": None}
        self._zone_states[key].update(kwargs)

    def get_device_on_state(self, dsuid: str) -> bool | None:
        """Get individual device OUTPUT on/off state (Joker-actor switch)."""
        return self._device_on_states.get(dsuid)

    def get_device_input_state(self, dsuid: str) -> bool | None:
        """Get individual device BINARY-INPUT active state (Joker binary_sensor)."""
        return self._device_input_states.get(dsuid)

    def get_device_runtime(self, dsuid: str) -> dict | None:
        """Get last-known runtime info for a device (on, is_present, ...)."""
        return self._device_runtime.get(dsuid)

    def set_device_on_state(self, dsuid: str, is_on: bool) -> None:
        """Set individual device OUTPUT on/off state (Joker-actor switch)."""
        self._device_on_states[dsuid] = is_on

    def set_device_input_state(self, dsuid: str, is_active: bool) -> None:
        """Set individual device BINARY-INPUT active state (Joker binary_sensor)."""
        self._device_input_states[dsuid] = is_active

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

    def is_apartment_state_active(self, name: str) -> bool:
        """Whether a dSS apartment system state (fire/rain/frost/hail/wind) is active."""
        return self._apartment_states.get(name, False)

    async def set_apartment_state(self, name: str, active: bool) -> None:
        """Set a dSS apartment system state, then update locally (optimistic)."""
        await self.api.set_apartment_state(name, active)
        self._apartment_states[name] = active
        self.async_update_listeners()

    async def set_custom_state(self, state_id: str, active: bool) -> None:
        """Set a Configurator User Defined State, optimistic local update.

        is_on on the switch reads the real addon-state back on the next fetch,
        so if the dSS ignores the write the switch returns to its true state.
        """
        # /json/state/set adresseert een state op z'n NAAM. We wisten alleen nog
        # niet ZEKER onder welke naam de dSS een handmatige custom-state registreert:
        # het numerieke id (beta8) en de DISPLAY-naam (beta9) werden BEIDE geweigerd
        # met "Not allowed or not existing system state name:<...>" (René 20 aug).
        # Daarom raden we niet nog een derde naam, maar PROBEREN we systematisch de
        # eindige set echte identifiers die de dSS ons zélf voor deze state gaf, in
        # volgorde van waarschijnlijkheid, en gebruiken we de eerste die de dSS
        # accepteert. Elke poging + dSS-antwoord wordt gelogd, zodat één schakelactie
        # de juiste naam definitief blootlegt (of aantoont dat het geen naam-, maar
        # een addon-scope-probleem is).
        cs = self._custom_states.get(state_id) or {}
        category = cs.get("category", "custom-states")

        if category != "custom-states":
            # Sensor-/computed-categorieën: completeName is en blijft de sleutel.
            write_name = cs.get("lookup_key") or state_id
            _LOGGER.debug("[DS-DEBUG] set_custom_state id=%s category=%s -> write_name=%s active=%s",
                         state_id, category, write_name, active)
            await self.api.set_custom_state(write_name, active)
        else:
            # Kandidaat-namen (gede-dupliceerd, None's eruit), meest waarschijnlijk eerst.
            # René's Network-capture bewees dat de dS-app de state adresseert op het
            # NUMERIEKE id (name=1689278590) via de addon-parameter — dus id eerst.
            # De andere namen blijven als robuuste fallback voor states die zich
            # eventueel onder een andere sleutel registreren.
            #  1) id            = numeriek id (== app-ground-truth)
            #  2) runtime_name  = de naam waaronder /usr/addon-states de state kent
            #  3) name          = display-naam
            #  4) lookup_key    = completeName indien aanwezig
            candidates = []
            for cand in (state_id, cs.get("runtime_name"), cs.get("name"),
                         cs.get("lookup_key")):
                if cand and cand not in candidates:
                    candidates.append(cand)
            _LOGGER.debug("[DS-DEBUG] set_custom_state id=%s category=%s name=%s "
                         "runtime_name=%s lookup_key=%s -> candidates=%s active=%s",
                         state_id, category, cs.get("name"), cs.get("runtime_name"),
                         cs.get("lookup_key"), candidates, active)
            last_err: DigitalStromApiError | None = None
            write_name = None
            attempts: list[str] = []
            for cand in candidates:
                try:
                    await self.api.set_custom_state(cand, active)
                    write_name = cand
                    _LOGGER.debug("[DS-DEBUG] custom-state write ACCEPTED by dSS with name=%s", cand)
                    break
                except DigitalStromApiError as err:
                    last_err = err
                    attempts.append(f"name={cand!r} -> {err}")
                    _LOGGER.warning("[DS-DEBUG] custom-state write REJECTED with name=%s: %s", cand, err)
            if write_name is None:
                # Geen enkele kandidaat werkte. beta8..10 logden de waarheid in
                # APARTE regels (coordinator-ERROR + per-kandidaat-WARNING), maar
                # René's log-paste begint steevast ÓP de switch-ERROR-regel, dus die
                # losse regels vielen elke keer buiten de plak. Daarom vouwen we nu
                # ALLES — versie, categorie, elke geprobeerde naam + het echte
                # dSS-antwoord, en de live in de dSS geregistreerde addon-state-namen —
                # in de ENE exception die switch.py logt. Zo bevat één regel de hele
                # grondwaarheid, ook als er verder niets wordt meegeplakt, en bevestigt
                # het "b11-diag" tegelijk dat deze build daadwerkelijk geladen is.
                try:
                    live = await self.api.get_addon_states("system-addon-user-defined-states")
                    registered = sorted(live.keys())
                except DigitalStromApiError:
                    registered = ["<addon-states query faalde>"]
                _LOGGER.error(
                    "[DS-DEBUG] custom-state write faalde voor id=%s met alle kandidaten %s. "
                    "In de dSS geregistreerde addon-state-namen: %s",
                    state_id, candidates, registered,
                )
                raise DigitalStromApiError(
                    f"[b11-diag] custom-state id={state_id} category={category} "
                    f"niet schrijfbaar via /json/state/set — dSS weigert ELKE identifier "
                    f"(dit is geen naam-, maar een mechanisme/rechten-probleem: de state "
                    f"bestaat en schakelt wél in de DS-app). Geprobeerd: [{'; '.join(attempts)}]. "
                    f"Live geregistreerde addon-state-namen op de dSS: {registered}"
                )

        if state_id in self._custom_states:
            self._custom_states[state_id]["state"] = "active" if active else "inactive"
            self._custom_states[state_id]["value"] = 1 if active else 2
        self.async_update_listeners()

    def set_apartment_state_local(self, name: str, active: bool) -> None:
        """Optimistically flag a system state locally WITHOUT writing to the dSS
        (used after a callScene trigger). The real value is corrected on the next
        /usr/states fetch — so if the dSS ignored the scene, is_on flips back to off."""
        self._apartment_states[name] = active

    @staticmethod
    def _norm_state(value) -> bool:
        """Normalise a /usr/states value to active=True. Handles dSS int (1=active,
        2=inactive), bool (day/night, daylight) and str (active/on/day vs inactive/off)."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return int(value) == 1
        if isinstance(value, str):
            return value.strip().lower() in ("active", "on", "true", "1", "day")
        return False

    def _is_tracked_state(self, name: str) -> bool:
        return (
            name in APARTMENT_SYSTEM_STATES
            or name in APARTMENT_ENV_STATES
            or bool(MOTION_STATE_RE.match(name))
            or name.endswith((".status.malfunction", ".status.service"))
        )

    async def fetch_dss_states(self) -> None:
        """One property query for all /usr/states; populate the tracked ones and
        discover the dynamic sets (motion zones, malfunction/service)."""
        states = await self.api.get_all_states()
        motion, malf, serv = [], [], []
        for s in states:
            name = s.get("name", "")
            if not name:
                continue
            m = MOTION_STATE_RE.match(name)
            if m:
                motion.append(int(m.group(1)))
            elif name.endswith(".status.malfunction"):
                malf.append(name)
            elif name.endswith(".status.service"):
                serv.append(name)
            elif name not in APARTMENT_SYSTEM_STATES and name not in APARTMENT_ENV_STATES:
                continue
            self._apartment_states[name] = self._norm_state(s.get("value"))
        self._motion_zones = sorted(set(motion))
        self._malfunction_names = malf
        self._service_names = serv

    async def fetch_outdoor_weather(self, data: dict | None = None) -> None:
        """Weather-service outdoor temperature + sun position (PRO). One call.

        data: an already-fetched getSensorValues response to reuse instead of
        making a fresh call. The main poll passes the result of
        fetch_sensor_data() here so getSensorValues runs only once per cycle
        (René, 25 aug 2026). Standalone callers pass nothing and we fetch."""
        try:
            res = data if data is not None else await self.api.get_sensor_values()
            outdoor = res.get("outdoor", {}) if isinstance(res, dict) else {}
            for k in ("temperature", "sunazimuth", "sunelevation"):
                node = outdoor.get(k)
                if isinstance(node, dict) and node.get("value") is not None:
                    self._outdoor[k] = node["value"]
        except Exception as err:
            _LOGGER.debug("Outdoor weather fetch failed: %s", err)

    @property
    def motion_zones(self) -> list[int]:
        return self._motion_zones

    def motion_active(self, zone_id: int) -> bool:
        return self._apartment_states.get(f"zone.{zone_id}.motion", False)

    def malfunction_active(self) -> bool:
        return any(self._apartment_states.get(n) for n in self._malfunction_names)

    def service_active(self) -> bool:
        return any(self._apartment_states.get(n) for n in self._service_names)

    def _affected_zones(self, names: list[str]) -> list[str]:
        out = []
        for n in names:
            if self._apartment_states.get(n):
                z = n.split(".")
                out.append(f"zone {z[1]} group {z[3]}" if len(z) > 3 else n)
        return out

    @property
    def malfunction_zones(self) -> list[str]:
        return self._affected_zones(self._malfunction_names)

    @property
    def service_zones(self) -> list[str]:
        return self._affected_zones(self._service_names)

    def outdoor_value(self, key: str) -> float | None:
        return self._outdoor.get(key)

    async def fetch_apartment_state(self) -> None:
        """Poll apartment presence state from dSS (free + pro, every cycle).

        stateChange events don't reliably fire on restart or when the dSS
        presence scene is set externally, so we re-read every poll cycle.
        """
        try:
            scene = await self.api.get_last_called_scene(0, 0)
            if scene >= 0 and scene in PRESENCE_SCENE_NUMBERS:
                if self._apartment_presence is None:
                    self._apartment_presence = scene
                    _LOGGER.info("Apartment presence initialized: scene %d", scene)
                elif scene != self._apartment_presence:
                    _LOGGER.info(
                        "Apartment presence changed (polled): %d → %d",
                        self._apartment_presence, scene,
                    )
                    self._apartment_presence = scene
                    self.async_update_listeners()
        except Exception as err:
            _LOGGER.debug("Could not poll apartment presence: %s", err)

    async def call_apartment_scene(self, scene: int) -> None:
        """Raise an apartment-wide system scene (Panic, Fire/Brand, Alarm 1-4, Presence).

        Uses /json/apartment/callScene so the scene fans out across ALL zones. The old
        zone/callScene(id=0) only hit the broadcast group on zone 0 — Panic worked that
        way but Alarm/Fire didn't propagate."""
        await self.api.apartment_call_scene(scene)

    async def undo_apartment_scene(self, scene: int) -> None:
        """Undo an apartment-wide system scene (explicit scene number)."""
        await self.api.apartment_undo_scene(scene)

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

    def get_joker_binary_input_devices_in_zone(self, zone_id: int) -> list[dict]:
        """Get Joker devices with binaryInputs AND outputMode > 0.

        Some devices (EnOcean window contacts, SW-UMR200) have outputMode > 0
        but also have binaryInputs for contact/state sensing. These should
        appear as binary sensors alongside their switch entity.
        Excludes devices already covered by get_joker_sensors_in_zone.
        """
        return [d for d in self.get_joker_devices_in_zone(zone_id)
                if d.get("output_mode", 0) > 0 and d.get("binary_inputs")]

    def get_umr200_devices(self) -> list[dict]:
        """SW-UMR200 actuators whose output is configured for VENTILATION.

        Identified by hwInfo (the UMR200 hardware) AND membership of the dS
        ventilation group (GROUP_VENTILATION = 10). René (28 aug 2026): a
        UMR200 configured as yellow (light, group 1) or black (Joker, group 8)
        must NOT get ventilation entities — only outputs that actually drive a
        ventilation unit. beta33 gated on hwInfo alone and so mislabelled every
        UMR200 (light/Joker included) as ventilation, with sensor/switch names
        wrongly containing "ventilatie". Gating on the colour group fixes that.

        René (28 aug 2026, correctie): his two Overloop outputs are configured
        as *Woningventilatie* in the dSS — a function of the blue climate colour
        group, NOT Joker — yet their device groups array surfaces only group 8,
        not GROUP_VENTILATION (10). The beta40 SEED-DIAG pinned the root cause:
        such an output reports ``groups=[8, 64]``. René confirmed (28 aug 2026)
        that de dSS group 64 (GROUP_HOME_VENTILATION) AUTOMATICALLY zodra een
        UMR200-poort op de blauwe Woningventilatie-functie wordt gezet. Group 64
        is therefore a reliable automatic marker: any UMR200 output carrying it
        is admitted without needing the manual whitelist.

        The opt-in ``self.extra_ventilation_dsuids`` whitelist (options flow) is
        kept as a harmless vangnet for exotic setups, but is no longer needed for
        a standard Woningventilatie output. Default whitelist is empty → the
        broad-mislabelling risk from beta33 (every UMR200 tagged as ventilation)
        stays gone: a UMR200 configured as light (group 1) or plain Joker
        (group 8 only, no 64) is still excluded.
        """
        out = []
        for dsuid, dev in self.devices.items():
            hw = (dev.get("hw_info") or "")
            if UMR200_HW_MARKER not in hw:
                continue
            if int(dev.get("output_mode", 0) or 0) <= 0:
                continue
            groups = dev.get("groups", [])
            in_vent_group = GROUP_VENTILATION in groups
            in_home_vent_group = GROUP_HOME_VENTILATION in groups
            whitelisted = dsuid.lower() in self.extra_ventilation_dsuids
            if not (in_vent_group or in_home_vent_group or whitelisted):
                continue
            out.append(dev)
        return out

    async def fetch_ventilation_outputs(self) -> None:
        """Read the raw relay output level of every SW-UMR200 output.

        getOutputValue (0..255) is the direct relay read — independent of the
        stale getDevices ``on`` cache and of the isOn divergence that plagues
        Joker actors. For each UMR200 we read both output offsets (0 and 1) and
        store raw + percentage. Runs on the ~1×/min vangnet cadence, so at most
        2 extra calls per UMR200 per minute.
        """
        for dev in self.get_umr200_devices():
            dsuid = dev.get("dsuid")
            if not dsuid:
                continue
            per_offset: dict[int, dict] = {}
            for offset in VENTILATION_OUTPUT_OFFSETS:
                seed_key = f"{dsuid}:{offset}"
                if seed_key in self._umr200_bad_offsets:
                    continue
                try:
                    raw = await self.api.get_device_output_value(dsuid, offset)
                except Exception as err:
                    _LOGGER.debug(
                        "UMR200 %s (%s) getOutputValue offset=%d faalde: %s",
                        dsuid[:12], dev.get("name", ""), offset, err,
                    )
                    fails = self._umr200_offset_fail_counts.get(seed_key, 0) + 1
                    self._umr200_offset_fail_counts[seed_key] = fails
                    if fails >= UMR200_OFFSET_FAIL_LIMIT:
                        self._umr200_bad_offsets.add(seed_key)
                        _LOGGER.info(
                            "UMR200 %s (%s) offset=%d faalt structureel (%dx) -- "
                            "wordt niet meer gepolld deze sessie (geen dS485-uitgang "
                            "op dit offset)",
                            dsuid[:12], dev.get("name", ""), offset, fails,
                        )
                    continue
                self._umr200_offset_fail_counts.pop(seed_key, None)
                raw = int(raw or 0)
                pct = round(max(0, min(255, raw)) / 255 * 100)
                per_offset[offset] = {"raw": raw, "pct": pct}

                # SEED-DIAG (beta40, René 28 aug 2026): once per session, dump the
                # startup seed trio for this UMR200 output so the "wrong initial
                # value after restart" is diagnosable at INFO (no debug needed).
                # A group-8+64 Woningventilatie output surfaces as BOTH a Joker
                # control switch (is_on = getState.isOn seed) AND a ventilation
                # status sensor (running = getOutputValue > threshold). If those
                # two disagree at boot, that IS the wrong initial value. Log both.
                if seed_key not in self._umr200_seed_logged:
                    self._umr200_seed_logged.add(seed_key)
                    running = pct > VENTILATION_ON_THRESHOLD_PCT
                    _LOGGER.info(
                        "UMR200 SEED-DIAG %s (%s | zone '%s') offset=%d: "
                        "getOutputValue raw=%d pct=%d%% -> ventilatiestatus running=%s "
                        "(drempel %d%%); joker-switch on_state=%s; groups=%s",
                        dsuid, dev.get("name", ""), dev.get("zone_name", ""), offset,
                        raw, pct, running, VENTILATION_ON_THRESHOLD_PCT,
                        self.get_device_on_state(dsuid), dev.get("groups", []),
                    )
            if per_offset:
                self._ventilation_outputs[dsuid] = per_offset

    def get_ventilation_output(self, dsuid: str, offset: int) -> dict | None:
        """Last-known {'raw', 'pct'} for a UMR200 output, or None if not polled yet."""
        return self._ventilation_outputs.get(dsuid, {}).get(offset)

    # =====================================================================
    # Event listener
    # =====================================================================

    async def start_event_listener(self) -> None:
        """Subscribe to events and start long-poll loop + binary input polling."""
        try:
            await self.api.subscribe_events()
            self._reconnect_delay = RECONNECT_INITIAL
        except DigitalStromApiError as err:
            _LOGGER.error("Failed to subscribe events: %s", err)
            return

        self._event_task = self.hass.async_create_background_task(
            self._event_loop(), f"{DOMAIN}_event_loop"
        )

        # Start fast binary input polling (contacts, doors, windows)
        self._binary_poll_task = self.hass.async_create_background_task(
            self._binary_poll_loop(), f"{DOMAIN}_binary_poll"
        )

        # Start power/energy polling as a background task (non-blocking, concurrent)
        self.hass.async_create_background_task(
            self._power_poll_loop(), f"{DOMAIN}_power_poll"
        )

    async def _binary_poll_loop(self) -> None:
        """Fast polling loop for binary input devices (every 5s).

        Contacts, door sensors, and window sensors need faster polling
        than the main 30s update cycle for responsive state tracking.
        """
        interval = self._binary_poll_interval
        _LOGGER.info("Binary poll loop STARTED (interval=%ds)", interval)
        poll_count = 0
        # Log-cadans schaalt mee met het interval: ~elke 5 min een levensteken.
        log_every = max(1, 300 // interval)
        while True:
            try:
                await asyncio.sleep(interval)
                await self.poll_binary_input_states()
                self.async_update_listeners()
                poll_count += 1
                if poll_count % log_every == 0:
                    _LOGGER.info("Binary poll loop alive: %d polls completed", poll_count)
            except asyncio.CancelledError:
                _LOGGER.info("Binary poll loop STOPPED")
                return
            except Exception as err:
                _LOGGER.warning("Binary poll loop error: %s", err)
                await asyncio.sleep(interval)

    async def _event_loop(self) -> None:
        """Continuously long-poll for events."""
        while True:
            try:
                events = await self.api.get_events()
                self._reconnect_delay = RECONNECT_INITIAL
                for event in events:
                    # One malformed event (e.g. a non-numeric sceneID) must never kill
                    # the whole event loop — log it and keep processing the rest.
                    try:
                        self._process_event(event)
                    except Exception as err:  # noqa: BLE001 - defensive, per-event
                        _LOGGER.warning("Skipping malformed dSS event %s: %s",
                                        event.get("name", "?"), err)

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

            except asyncio.TimeoutError:
                _LOGGER.debug("Event poll timed out, retrying")
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

        if name == "buttonClick":
            source = event.get("source") or {}
            dsuid = source.get("dsid") or source.get("dSUID") or ""
            if dsuid and self.entry_id:
                async_dispatcher_send(
                    self.hass,
                    signal_button_event(self.entry_id),
                    {
                        "dsuid": dsuid,
                        "button_index": props.get("buttonIndex"),
                        "click_type": props.get("clickType"),
                    },
                )
            return

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
                if name == "callScene":
                    is_on = self.zone_on_after_scene(zone_id, group, scene)
                else:  # undoScene = terug naar vorige stand -> behandel als aan
                    is_on = True
                self.set_zone_state(zone_id, group, scene=scene, is_on=is_on)

                # Update individual device states for Joker group scenes.
                # Alleen ACTOREN (outputMode>0): een scene stuurt de relais-output.
                # Pure ingang-sensoren volgen hun eigen binary-input, niet de scene.
                if group == GROUP_JOKER:
                    for dev in self.get_joker_actuators_in_zone(zone_id):
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

        elif name == "addonStateChange":
            # dSS fires addonStateChange for states managed by the user-defined-states
            # addon (system-addon-user-defined-states). Without subscribing to this
            # event the user_states cache never gets live updates after init.
            state_name = props.get("statename") or props.get("name") or ""
            state_value = props.get("state", "") or props.get("value", "")
            if not state_name:
                _LOGGER.debug("addonStateChange without statename, ignored: %s", props)
                return
            state_str = state_value.lower() if isinstance(state_value, str) else state_value
            value_norm: int | str = state_str
            if state_str in ("active", "1"):
                value_norm = STATE_VALUE_ACTIVE
            elif state_str in ("inactive", "2"):
                value_norm = 2
            # Update both apartment-wide user states and configurator custom states
            matched_id = self._find_custom_state_by_key(state_name) if hasattr(self, "_find_custom_state_by_key") else None
            if matched_id:
                self.update_custom_state_runtime(matched_id, str(state_value), value_norm if isinstance(value_norm, int) else None)
            self._user_states[state_name] = {
                "state": str(state_value),
                "value": value_norm,
            }
            _LOGGER.debug(
                "addonStateChange: %s = %s (value=%s)",
                state_name, state_value, value_norm,
            )
            self.async_update_listeners()

        elif name == "stateChange":
            dsuid = props.get("dsuid", "")
            state_name = props.get("statename", "")
            state_value = props.get("state", "")

            # Apartment-level state changes (rain, etc.) — no dsuid
            # dSS format: StateApartment;rain;1;active / StateApartment;rain;2;inactive
            if self._is_tracked_state(state_name):
                # fire/rain/alarm + day-night/holiday + motion + malfunction/service
                self._apartment_states[state_name] = self._norm_state(state_value)
                _LOGGER.debug(
                    "dSS state change: %s=%s", state_name, state_value,
                )
                self.async_update_listeners()
            elif state_name == "heating_system_mode":
                # Heating controller: active/1=heating, inactive/2/off/cooling=cooling
                was_cooling = self._heating_system_cooling
                self._heating_system_cooling = str(state_value).lower() in (
                    "inactive", "off", "cooling", "2",
                )
                if was_cooling != self._heating_system_cooling:
                    _LOGGER.info(
                        "Heating system mode change: %s → cooling=%s",
                        state_value, self._heating_system_cooling,
                    )
                    self.async_update_listeners()
            elif state_name and self._find_custom_state_by_key(state_name):
                # Configurator User Defined State change — match on id OR lookup_key
                matched_id = self._find_custom_state_by_key(state_name)
                state_str = state_value.lower() if isinstance(state_value, str) else str(state_value)
                value_norm: int | None = None
                if state_str in ("active", "1"):
                    value_norm = STATE_VALUE_ACTIVE
                elif state_str in ("inactive", "2"):
                    value_norm = 2
                self.update_custom_state_runtime(matched_id, str(state_value), value_norm)
                _LOGGER.debug(
                    "Custom state change: %s (%s) = %s",
                    state_name, matched_id, state_value,
                )
                self.async_update_listeners()
            elif state_name and state_name in self._user_states:
                # User Defined / apartment-wide state change (named state, no dsuid)
                new_val = state_value
                # dSS sometimes reports numeric value as string; normalize binary states
                state_str = state_value.lower() if isinstance(state_value, str) else state_value
                value_norm = state_str
                if state_str in ("active", "1"):
                    value_norm = STATE_VALUE_ACTIVE
                elif state_str in ("inactive", "2"):
                    value_norm = 2
                self._user_states[state_name] = {
                    "state": str(state_value),
                    "value": value_norm,
                }
                _LOGGER.debug(
                    "User state change: %s = %s (value=%s)",
                    state_name, state_value, value_norm,
                )
                self.async_update_listeners()
            elif dsuid:
                # Binary input state changes (contacts, smoke, etc.)
                # Match dsuid case-insensitively and handle truncated dsuid from some dSS versions
                _LOGGER.debug(
                    "stateChange event for device: dsuid=%s statename=%s state=%s",
                    dsuid[:16], state_name, state_value,
                )
                matched_dsuid = dsuid if dsuid in self.devices else None
                if not matched_dsuid:
                    # Try prefix match (some events use shortened dsuid)
                    for known_dsuid in self.devices:
                        if known_dsuid.startswith(dsuid) or dsuid.startswith(known_dsuid):
                            matched_dsuid = known_dsuid
                            break
                if matched_dsuid:
                    is_active = state_value.lower() in ("active", "true", "1", "open")
                    # Binaire-ingang-event → INPUT-slot (leest de binary_sensor), los van
                    # de relais-output van dezelfde actor.
                    self.set_device_input_state(matched_dsuid, is_active)
                    _LOGGER.debug(
                        "State change MATCHED: dsuid=%s matched=%s state=%s value=%s",
                        dsuid[:8], matched_dsuid[:8], state_name, state_value,
                    )
                    self.async_update_listeners()
                else:
                    _LOGGER.debug(
                        "State change UNMATCHED: dsuid=%s state=%s value=%s",
                        dsuid[:16], state_name, state_value,
                    )

    # =====================================================================
    # Polling (DataUpdateCoordinator)
    # =====================================================================

    async def _async_update_data(self) -> dict:
        """Periodic poll for consumption + temperature + sensors."""
        try:
            # New cycle: no fresh apartment sensor cache yet.
            self._zone_sensors_fresh = False
            sensor_data = None

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

            # PRO: fetch the apartment-wide getSensorValues BEFORE mapping device
            # sensors, so fetch_device_sensors maps THIS cycle's fresh data exactly
            # once (and can fall back to the per-zone vangnet if this fetch failed).
            # The response is reused below for the outdoor/sun read — still one
            # apartment-wide call per cycle (René, 26 aug 2026).
            if self.pro_enabled:
                sensor_data = await self.fetch_sensor_data()

            # Device sensors: Ulux, thermostats, etc. (FREE per-zone loop / PRO map)
            await self.fetch_device_sensors()

            # Binary input states: handled by separate fast poll loop (_binary_poll_loop)

            # Apartment presence mode: poll every cycle (free + pro).
            # Events don't fire reliably on restart or external scene changes.
            await self.fetch_apartment_state()

            # Joker-ACTOR output-stand LIVE herbevestigen (getState.isOn). callScene-
            # events houden de switch tussendoor live; deze refresh is het vangnet
            # voor gemiste events en vervangt de vroegere (onbetrouwbare) stale-cache-
            # uitlezing in de 5s binary-poll (René, SW-KL200, 22 aug 2026). Kost tot
            # ~2×N calls/cyclus (getState + getOutputValue per actor), dus draait als
            # vangnet op ~1×/min i.p.v. elke hoofdcyclus (René, 26 aug 2026).
            poll_now = _time.time()
            if poll_now - self._last_joker_confirm >= self._vangnet_due_threshold:
                self._last_joker_confirm = poll_now
                await self.fetch_joker_actuator_states()
                # SW-UMR200 ventilation output levels ride the same vangnet cadence
                # (2 getOutputValue calls per UMR200 per minute — negligible load).
                await self.fetch_ventilation_outputs()

            # dSS /usr/states backup-poll (events keep these live in between).
            await self.fetch_dss_states()

            # Custom (Configurator) states: fetched once at startup in
            # __init__.py (best-effort). If that attempt failed or raced the
            # dSS on a fresh restart, self._custom_states stays permanently
            # empty and switches like "Vrije tijd" report unknown forever
            # (the addonStateChange handler can only update existing keys,
            # never add). Retry here until it succeeds; once populated this
            # is a no-op, so there is no extra steady-state dSS load.
            if not self._custom_states:
                try:
                    await self.fetch_custom_states()
                except Exception as err:  # never break the poll cycle
                    _LOGGER.debug("Custom states retry fetch failed: %s", err)

            # Pro features: extra data. getTemperatureControlValues is already
            # fetched above (skip_temp_prefetch), and getSensorValues was fetched
            # once earlier this cycle (sensor_data) and is reused for the
            # outdoor/sun read — no duplicate apartment-wide dSS calls per cycle
            # (René, 25 + 26 aug 2026).
            if self.pro_enabled:
                # De per-zone climate-status-poll (getTemperatureControlStatus per
                # zone, ~N calls) is ook alleen vangnet — stateChange-events houden
                # de setpoints/mode tussendoor live. Draai 'm op dezelfde ~1×/min
                # vangnet-cadans i.p.v. elke hoofdcyclus (René, 26 aug 2026). De
                # getTemperatureControlValues-prefetch is al deze cyclus gedaan, dus
                # blijft skip_temp_prefetch=True.
                climate_now = _time.time()
                if climate_now - self._last_climate_poll >= self._vangnet_due_threshold:
                    self._last_climate_poll = climate_now
                    await self.fetch_climate_data(skip_temp_prefetch=True)
                await self.fetch_outdoor_weather(data=sensor_data)

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

        # Periodically re-validate the Pro license (every 6h). Picks up a
        # server-side rebind after a firmware-update id-flip without an HA
        # restart, and keeps the "Pro inactive" repair issue in sync.
        if self.pro_license_key and (now - self._license_last_check > 21600):
            self._license_last_check = now
            self.hass.async_create_task(self._recheck_license())

        return {
            "consumption": self._consumption,
            "temperatures": self._temperatures,
        }

    async def _recheck_license(self) -> None:
        """Re-validate the Pro license; reload the entry if Pro status changed.

        A dSS firmware update can flip the dSS id and temporarily unbind the
        license server-side. Once it is re-bound, this picks the change up
        within ~6h instead of only on the next HA restart. Free<->Pro changes
        the set of platforms, so a status flip triggers a config-entry reload.
        """
        try:
            result = await check_pro_license(self.pro_license_key, self.dss_id)
        except Exception as err:  # never let a recheck break the poll loop
            _LOGGER.debug("License recheck failed (non-fatal): %s", err)
            return
        was_enabled = self.pro_enabled
        self.license_info = result
        sync_pro_issue(self.hass, self.entry_id, True, result["valid"])
        if result["valid"] != was_enabled and self.entry_id:
            _LOGGER.info(
                "Pro license status changed (%s -> %s) — reloading entry",
                was_enabled, result["valid"],
            )
            self.pro_enabled = result["valid"]
            self.hass.config_entries.async_schedule_reload(self.entry_id)

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
        for task in (self._event_task, self._binary_poll_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await self.api.close()
