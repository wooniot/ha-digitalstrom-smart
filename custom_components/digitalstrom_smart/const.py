"""Constants for Digital Strom Smart integration by Woon IoT BV.

The definitive Digital Strom integration for Home Assistant.
Created by Marijn Nederlof — Heerjansdam, NL.
"""

DOMAIN = "digitalstrom_smart"
MANUFACTURER = "Digital Strom"
INTEGRATION_AUTHOR = "Woon IoT BV"
INTEGRATION_AUTHOR_ID = "MN-HJD-2026"
INTEGRATION_URL = "https://github.com/wooniot/ha-digitalstrom-smart"
INTEGRATION_VERSION = "4.1.9"

# Application name shown in dSS Configurator under registered applications
DSS_APP_NAME = "WoonIoT HA Connect"

# Telemetry endpoint (opt-in, anonymous)
TELEMETRY_URL = "https://ha-ds.internetist.nl/ha-ds/ping"

# Pro license check endpoint
PRO_LICENSE_URL = "https://ha-ds.internetist.nl/ha-ds/license"

# Connection type (local only - direct network access to dSS)
CONN_LOCAL = "local"

# --- dS Group IDs ---
GROUP_BROADCAST = 0
GROUP_LIGHT = 1
GROUP_SHADE = 2
GROUP_HEATING = 3
GROUP_AUDIO = 4
GROUP_VIDEO = 5
GROUP_SECURITY = 6
GROUP_ACCESS = 7
GROUP_JOKER = 8       # Black devices (switches, etc.)
GROUP_COOLING = 9
GROUP_VENTILATION = 10
GROUP_WINDOW = 11
GROUP_TEMP_CONTROL = 48
# "Woningventilatie" (apartment/home ventilation). René (DS expert, 28 aug 2026,
# bevestigd): de dSS kent groep 64 AUTOMATISCH toe zodra een SW-UMR200-poort in
# de configurator op de blauwe Woningventilatie-functie wordt gezet. Zo'n uitgang
# rapporteert in zijn device-groups géén GROUP_VENTILATION (10) maar wél 64 (naast
# Joker 8) — zie de beta40 SEED-DIAG (groups=[8, 64]). Groep 64 is dus de
# betrouwbare automatische marker voor een woningventilatie-uitgang en vervangt de
# handmatige opt-in whitelist (die als vangnet blijft bestaan, leeg by default).
GROUP_HOME_VENTILATION = 64

GROUP_NAMES = {
    GROUP_LIGHT: "Light",
    GROUP_SHADE: "Shade",
    GROUP_HEATING: "Heating",
    GROUP_AUDIO: "Audio",
    GROUP_VIDEO: "Video",
    GROUP_SECURITY: "Security",
    GROUP_ACCESS: "Access",
    GROUP_JOKER: "Joker",
    GROUP_COOLING: "Cooling",
    GROUP_VENTILATION: "Ventilation",
    GROUP_WINDOW: "Window",
    GROUP_TEMP_CONTROL: "Temperature Control",
    GROUP_HOME_VENTILATION: "Home Ventilation",
}

# Groups that may legitimately be configured at ZONE level without a physical
# device present. Climate/HVAC control on the dSS is zone-based, so heating,
# cooling, ventilation and temperature-control can exist on a zone that has no
# dedicated actuator device. All OTHER groups (shade, light, audio, ...) require
# a real actuator device and must therefore only be derived from device groups —
# otherwise phantom entities appear in rooms that have no such device (e.g. a
# cover entity in a room without any blinds/screens). See _parse_structure().
ZONE_LEVEL_GROUPS = {
    GROUP_HEATING,
    GROUP_COOLING,
    GROUP_VENTILATION,
    GROUP_TEMP_CONTROL,
}

# --- dS Scene Numbers ---
SCENE_OFF = 0
SCENE_1 = 5       # Preset 1 (usually "on" / max)
SCENE_2 = 17      # Preset 2
SCENE_3 = 18      # Preset 3
SCENE_4 = 19      # Preset 4
SCENE_MAX = 5     # Same as Scene 1
SCENE_MIN = 0     # Off
SCENE_STOP = 15   # Stop (covers, dimming)

# Apartment-wide scenes: Presence
SCENE_PRESENT = 71       # Coming home / Thuis
SCENE_ABSENT = 72        # Leaving home / Afwezig
SCENE_SLEEPING = 69      # Slapen
SCENE_WAKEUP = 70        # Opstaan
SCENE_STANDBY = 67       # Standby
SCENE_DEEP_OFF = 68      # Diep uit

# Apartment-wide scenes: Alarm & Safety
SCENE_PANIC = 65         # Paniek
SCENE_DOOR_BELL = 73     # Deurbel
SCENE_ALARM_1 = 74       # Alarm 1
SCENE_ALARM_2 = 75       # Alarm 2
SCENE_ALARM_3 = 76       # Alarm 3 (Brand)
SCENE_ALARM_4 = 77       # Alarm 4
SCENE_FIRE = 76          # Brand (= Alarm 3)
SCENE_RAIN = 85          # Regen bescherming

# Legacy alias
SCENE_ALARM = 74

# Presence scene mapping: scene_nr -> display name
APARTMENT_PRESENCE_SCENES = {
    SCENE_PRESENT: "Present",
    SCENE_ABSENT: "Absent",
    SCENE_SLEEPING: "Sleeping",
    SCENE_WAKEUP: "Wakeup",
    SCENE_STANDBY: "Standby",
    SCENE_DEEP_OFF: "Deep Off",
}

# Presence scene mapping: scene_nr -> translation key (for select entity)
APARTMENT_PRESENCE_KEYS = {
    SCENE_PRESENT: "present",
    SCENE_ABSENT: "absent",
    SCENE_SLEEPING: "sleeping",
    SCENE_WAKEUP: "wakeup",
    SCENE_STANDBY: "standby",
    SCENE_DEEP_OFF: "deep_off",
}

# All presence scene numbers (for detection in events)
PRESENCE_SCENE_NUMBERS = set(APARTMENT_PRESENCE_SCENES.keys())

# User-triggerable apartment scenes that propagate via /json/apartment/callScene:
# only Panic and Doorbell. (Alarm 1-4 and Fire are dSS *states* set by the alarm/weather
# system — read-only, see APARTMENT_SYSTEM_STATES. callScene for the alarm scenes is a
# no-op on the dSS and /json/state/set is rejected, so they cannot be triggered from HA.)
APARTMENT_ALARM_SCENES = {
    SCENE_PANIC: "Panic",
    SCENE_DOOR_BELL: "Doorbell",
}

ALARM_TRANSLATION_KEYS = {
    SCENE_PANIC: "panic",
    SCENE_DOOR_BELL: "doorbell",
}

ALARM_BINARY_SENSOR_KEYS = {
    SCENE_PANIC: "panic_active",
    SCENE_DOOR_BELL: "doorbell_active",
}

# dSS apartment system states (/usr/states; value 1=active, 2=inactive). Exposed as
# READ-ONLY binary_sensors. These are set by the dSS itself (weather service, smoke/alarm
# devices) and are NOT user-settable: /json/state/set is rejected and callScene doesn't
# drive them, so there is deliberately NO switch. bin_uid keeps the legacy unique_id
# (fire/rain/alarm 1·2·4) so existing entities survive.
#   device_class strings map to BinarySensorDeviceClass in binary_sensor.py.
APARTMENT_SYSTEM_STATES = {
    "fire":   {"name": "Fire",    "tkey": "fire",            "device_class": "smoke",    "icon": "mdi:fire",            "bin_uid": "alarm_76"},
    "rain":   {"name": "Rain",    "tkey": "rain_protection", "device_class": "moisture", "icon": "mdi:weather-pouring", "bin_uid": "weather_85"},
    "frost":  {"name": "Frost",   "tkey": "frost",           "device_class": "cold",     "icon": "mdi:snowflake",      "bin_uid": "state_frost"},
    "hail":   {"name": "Hail",    "tkey": "hail",            "device_class": None,       "icon": "mdi:weather-hail",   "bin_uid": "state_hail"},
    "wind":   {"name": "Wind",    "tkey": "wind",            "device_class": None,       "icon": "mdi:weather-windy",  "bin_uid": "state_wind"},
    "alarm":  {"name": "Alarm 1", "tkey": "alarm_1_active",  "device_class": "safety",   "icon": "mdi:alarm-light",     "bin_uid": "alarm_74"},
    "alarm2": {"name": "Alarm 2", "tkey": "alarm_2_active",  "device_class": "safety",   "icon": "mdi:alarm-light",     "bin_uid": "alarm_75"},
    "alarm3": {"name": "Alarm 3", "tkey": "alarm_3_active",  "device_class": "safety",   "icon": "mdi:alarm-light",     "bin_uid": "state_alarm3"},
    "alarm4": {"name": "Alarm 4", "tkey": "alarm_4_active",  "device_class": "safety",   "icon": "mdi:alarm-light",     "bin_uid": "alarm_77"},
}

# User-triggerable system alarm scenes (Fire/Brand + Alarm 1-4). Per dS hoofd-
# ontwikkeling: "fire is a scene call, scene calls work via api" — dus deze worden
# afgevuurd met /json/apartment/callScene (NIET /json/state/set, dat wordt geweigerd).
# Naast de READ-ONLY status-binary_sensor (APARTMENT_SYSTEM_STATES) krijgt elk hiervan
# ook een SWITCH om te activeren. is_on leest de ECHTE /usr/states-waarde terug (key =
# state-id), dus negeert de dSS een scene → de switch klapt meteen terug naar uit: eerlijke
# feedback. scene = apartment-scene-nummer; tkey = bestaande switch-vertaalsleutel.
APARTMENT_TRIGGER_SCENES = {
    "fire":   {"scene": SCENE_FIRE,    "tkey": "fire",    "icon": "mdi:fire"},
    "alarm":  {"scene": SCENE_ALARM_1, "tkey": "alarm_1", "icon": "mdi:alarm-light"},
    "alarm2": {"scene": SCENE_ALARM_2, "tkey": "alarm_2", "icon": "mdi:alarm-light-outline"},
    "alarm3": {"scene": SCENE_ALARM_3, "tkey": "alarm_3", "icon": "mdi:alarm-light"},
    "alarm4": {"scene": SCENE_ALARM_4, "tkey": "alarm_4", "icon": "mdi:alert"},
}

# Environment states from /usr/states (solar computer / presence simulator). FREE,
# read-only binary sensors. Values are bool (day/night, daylight, twilight) or a
# string ("on"/"off" for holiday) — normalised in coordinator._norm_state().
APARTMENT_ENV_STATES = {
    "daynight": {"tkey": "daynight", "device_class": None,    "icon": "mdi:theme-light-dark",    "bin_uid": "state_daynight"},
    "twilight": {"tkey": "twilight", "device_class": None,    "icon": "mdi:weather-sunset",      "bin_uid": "state_twilight"},
    "daylight": {"tkey": "daylight", "device_class": "light", "icon": "mdi:white-balance-sunny", "bin_uid": "state_daylight"},
    "holiday":  {"tkey": "holiday",  "device_class": None,    "icon": "mdi:bag-suitcase",        "bin_uid": "state_holiday"},
}

# Regex for per-zone motion states: zone.<id>.motion  (PRO, device_class motion)
import re as _re
MOTION_STATE_RE = _re.compile(r"^zone\.(\d+)\.motion$")

# Weather protection: scene_nr -> translation key
WEATHER_TRANSLATION_KEYS = {
    SCENE_RAIN: "rain_protection",
}

# Weather protection scenes — read-only binary sensors, not switches
# Note: Wind Protection removed — dSS handles wind blocking per device internally,
# there is no universal wind protection state. Users can use User Defined States.
APARTMENT_WEATHER_SCENES = {
    SCENE_RAIN: "Rain",
}

# All alarm scene numbers (for detection in events) — includes weather protection
ALARM_SCENE_NUMBERS = set(APARTMENT_ALARM_SCENES.keys()) | set(APARTMENT_WEATHER_SCENES.keys())

# Cover scenes
SCENE_COVER_OPEN = 5    # Up / Open
SCENE_COVER_CLOSE = 0   # Down / Close
SCENE_COVER_STOP = 15   # Stop
SCENE_COVER_SUN_PROTECT = 11  # Sun protection position
SCENE_COVER_WIND_PROTECT = 71  # Wind protection (fully open)

# --- dS Area Scene Numbers ---
# GEVERIFIEERD tegen de officiële dS scene-tabel (openHAB SceneEnum) + velddata
# (GitHub #26) + melding #35. Elk area heeft precies één OFF- en één ON-scene op
# zone/groep-niveau:
#   Area 1: uit = 1, aan = 6 | Area 2: uit = 2, aan = 7
#   Area 3: uit = 3, aan = 8 | Area 4: uit = 4, aan = 9
# (scene 0 = hele zone uit, 5 = hele zone aan / preset 1.)
# Er bestaan GEEN "Area x scene 1/2/3/4" — de vorige nummering (6/10/20/30 als
# area-off) was fout en gaf verkeerde entity_id's (GitHub #35).
SCENE_AREA1_OFF = 1
SCENE_AREA1_ON = 6
SCENE_AREA2_OFF = 2
SCENE_AREA2_ON = 7
SCENE_AREA3_OFF = 3
SCENE_AREA3_ON = 8
SCENE_AREA4_OFF = 4
SCENE_AREA4_ON = 9

# --- dS Area aan/uit-scenes voor zone is_on-detectie ---
# BEVESTIGD met velddata (Urs Frischknecht, GitHub #26, 28 jun 2026) en de
# officiële dS scene-tabel: de fysieke schakelaar stuurt per area een ON- en
# een OFF-scene. Dit is dezelfde nummering als de SCENE_AREA*-constanten
# hierboven (nu gelijkgetrokken).
AREA_ON_SCENES = {6: 1, 7: 2, 8: 3, 9: 4}   # scene -> area-index (area aan)
AREA_OFF_SCENES = {1: 1, 2: 2, 3: 3, 4: 4}  # scene -> area-index (area uit)

# Extended presets (Preset 10-44) — scene-nummers per dS scene-tabel.
EXTENDED_PRESET_NAMES = {
    32: "Preset 10", 33: "Preset 11", 20: "Preset 12", 21: "Preset 13", 22: "Preset 14",
    34: "Preset 20", 35: "Preset 21", 23: "Preset 22", 24: "Preset 23", 25: "Preset 24",
    36: "Preset 30", 37: "Preset 31", 26: "Preset 32", 27: "Preset 33", 28: "Preset 34",
    38: "Preset 40", 39: "Preset 41", 29: "Preset 42", 30: "Preset 43", 31: "Preset 44",
}

# All zone-level scene numbers that can be user-configured
# Excludes apartment-wide scenes (65+) which are handled separately
ALL_ZONE_SCENES = [
    SCENE_OFF, SCENE_1, SCENE_2, SCENE_3, SCENE_4,     # Preset 0-4
    SCENE_AREA1_OFF, SCENE_AREA2_OFF, SCENE_AREA3_OFF, SCENE_AREA4_OFF,  # Area 1-4 uit (1-4)
    SCENE_AREA1_ON, SCENE_AREA2_ON, SCENE_AREA3_ON, SCENE_AREA4_ON,      # Area 1-4 aan (6-9)
    *EXTENDED_PRESET_NAMES.keys(),  # Preset 10-44
]

# Named scene defaults per group
NAMED_SCENES = {
    SCENE_OFF: "Off",
    SCENE_1: "Scene 1",
    SCENE_2: "Scene 2",
    SCENE_3: "Scene 3",
    SCENE_4: "Scene 4",
}

# Default names for area/extended scenes (used when dSS has no custom name).
# Area scenes: elk area heeft één OFF (1-4) en één ON (6-9). GEVERIFIEERD
# tegen de officiële dS scene-tabel + melding #35.
AREA_SCENE_NAMES = {
    SCENE_AREA1_OFF: "Area 1 Off",
    SCENE_AREA2_OFF: "Area 2 Off",
    SCENE_AREA3_OFF: "Area 3 Off",
    SCENE_AREA4_OFF: "Area 4 Off",
    SCENE_AREA1_ON: "Area 1 On",
    SCENE_AREA2_ON: "Area 2 On",
    SCENE_AREA3_ON: "Area 3 On",
    SCENE_AREA4_ON: "Area 4 On",
    **EXTENDED_PRESET_NAMES,
}

NAMED_SCENES_SHADE = {
    SCENE_OFF: "Close",
    SCENE_1: "Open",
    SCENE_2: "Shade Preset 2",
    SCENE_3: "Shade Preset 3",
    SCENE_4: "Shade Preset 4",
}

GROUP_HEATING_SCENES = {
    SCENE_OFF: "Protection",
    SCENE_1: "Comfort",
    SCENE_2: "Economy",
    SCENE_3: "Night",
    SCENE_4: "Holiday",
}

# Scene translation keys: (group, scene_nr) -> translation key
# Used for default/fallback scene names. User-defined scenes from dSS keep their original name.
SCENE_TRANSLATION_KEYS = {
    # Light
    (GROUP_LIGHT, SCENE_OFF): "light_off",
    (GROUP_LIGHT, SCENE_1): "light_scene_1",
    (GROUP_LIGHT, SCENE_2): "light_scene_2",
    (GROUP_LIGHT, SCENE_3): "light_scene_3",
    (GROUP_LIGHT, SCENE_4): "light_scene_4",
    # Shade
    (GROUP_SHADE, SCENE_OFF): "shade_close",
    (GROUP_SHADE, SCENE_1): "shade_open",
    (GROUP_SHADE, SCENE_2): "shade_preset_2",
    (GROUP_SHADE, SCENE_3): "shade_preset_3",
    (GROUP_SHADE, SCENE_4): "shade_preset_4",
    # Heating
    (GROUP_HEATING, SCENE_OFF): "heating_protection",
    (GROUP_HEATING, SCENE_1): "heating_comfort",
    (GROUP_HEATING, SCENE_2): "heating_economy",
    (GROUP_HEATING, SCENE_3): "heating_night",
    (GROUP_HEATING, SCENE_4): "heating_holiday",
    # Area scenes — elk area heeft één OFF (1-4) en één ON (6-9).
    # Area 1 (uit=1, aan=6)
    (GROUP_LIGHT, SCENE_AREA1_OFF): "light_area1_off",
    (GROUP_LIGHT, SCENE_AREA1_ON): "light_area1_on",
    (GROUP_SHADE, SCENE_AREA1_OFF): "shade_area1_off",
    (GROUP_SHADE, SCENE_AREA1_ON): "shade_area1_on",
    # Area 2 (uit=2, aan=7)
    (GROUP_LIGHT, SCENE_AREA2_OFF): "light_area2_off",
    (GROUP_LIGHT, SCENE_AREA2_ON): "light_area2_on",
    (GROUP_SHADE, SCENE_AREA2_OFF): "shade_area2_off",
    (GROUP_SHADE, SCENE_AREA2_ON): "shade_area2_on",
    # Area 3 (uit=3, aan=8)
    (GROUP_LIGHT, SCENE_AREA3_OFF): "light_area3_off",
    (GROUP_LIGHT, SCENE_AREA3_ON): "light_area3_on",
    (GROUP_SHADE, SCENE_AREA3_OFF): "shade_area3_off",
    (GROUP_SHADE, SCENE_AREA3_ON): "shade_area3_on",
    # Area 4 (uit=4, aan=9)
    (GROUP_LIGHT, SCENE_AREA4_OFF): "light_area4_off",
    (GROUP_LIGHT, SCENE_AREA4_ON): "light_area4_on",
    (GROUP_SHADE, SCENE_AREA4_OFF): "shade_area4_off",
    (GROUP_SHADE, SCENE_AREA4_ON): "shade_area4_on",
}

# Outdoor sensor key -> translation key
OUTDOOR_SENSOR_TRANSLATION_KEYS = {
    "temperature": "outdoor_temperature",
    "humidity": "outdoor_humidity",
    "brightness": "outdoor_brightness",
    "windspeed": "wind_speed",
    "windgust": "wind_gust",
    "airpressure": "air_pressure",
    "rain": "rain_intensity",
}

# --- Ventilation (SW-UMR200 outputs) ---
# A SW-UMR200 always has exactly 2 outputs (offset 0 and 1). When an output
# drives a ventilation unit, its running level is the raw relay output value
# (getOutputValue, 0..255). René (DS expert, 27 aug 2026): treat >10% as ON,
# <=10% as OFF, so a stationary ~5% rest level reads as OFF (the plain >0
# actor logic would wrongly show ON). 10% of 255 = 25.5, so raw > 25 is ON.
VENTILATION_ON_THRESHOLD_PCT = 10
VENTILATION_OUTPUT_OFFSETS = (0, 1)
UMR200_HW_MARKER = "UMR200"
# René (28 aug 2026): in de praktijk beantwoordt niet elke UMR200-dsuid beide
# offsets — getOutputValue offset=1 faalt structureel op single-output units
# met een echte dS485-busfout (DS485d Socket Error -17 invalid parameter),
# niet een onschuldige cache-miss. Na dit aantal opeenvolgende mislukkingen
# per dsuid/offset wordt die combinatie voor de rest van de sessie
# overgeslagen (self-healing bij herstart / structuurwijziging).
UMR200_OFFSET_FAIL_LIMIT = 3

# --- dS Sensor Types ---
SENSOR_ACTIVE_POWER = 4    # Watt — SW-KL200, SW-ZWS200, SW-SSL200, SW-UMR200
SENSOR_ACTIVE_ENERGY = 5   # Wh cumulative — SW-KL200, SW-ZWS200, SW-SSL200, SW-UMR200
SENSOR_TEMPERATURE = 9
SENSOR_HUMIDITY = 13
SENSOR_BRIGHTNESS = 11
SENSOR_CO2 = 21
SENSOR_SOUND = 25
SENSOR_WIND_SPEED = 14
SENSOR_WIND_GUST = 15
SENSOR_WIND_DIRECTION = 16
SENSOR_RAIN = 17
SENSOR_AIR_PRESSURE = 18

# Device sensor type -> translation key
DEVICE_SENSOR_TRANSLATION_KEYS = {
    SENSOR_ACTIVE_POWER: "device_power",
    SENSOR_ACTIVE_ENERGY: "device_energy",
    SENSOR_TEMPERATURE: "device_temperature",
    SENSOR_HUMIDITY: "device_humidity",
    SENSOR_BRIGHTNESS: "device_brightness",
    SENSOR_CO2: "device_co2",
}

SENSOR_TYPE_NAMES = {
    SENSOR_ACTIVE_POWER: "Power",
    SENSOR_ACTIVE_ENERGY: "Energy",
    SENSOR_TEMPERATURE: "Temperature",
    SENSOR_HUMIDITY: "Humidity",
    SENSOR_BRIGHTNESS: "Brightness",
    SENSOR_CO2: "CO2",
    SENSOR_SOUND: "Sound Level",
    SENSOR_WIND_SPEED: "Wind Speed",
    SENSOR_WIND_GUST: "Wind Gust",
    SENSOR_WIND_DIRECTION: "Wind Direction",
    SENSOR_RAIN: "Rain",
    SENSOR_AIR_PRESSURE: "Air Pressure",
}

SENSOR_TYPE_UNITS = {
    SENSOR_ACTIVE_POWER: "W",
    SENSOR_ACTIVE_ENERGY: "Wh",
    SENSOR_TEMPERATURE: "°C",
    SENSOR_HUMIDITY: "%",
    SENSOR_BRIGHTNESS: "lx",
    SENSOR_CO2: "ppm",
    SENSOR_SOUND: "dB",
    SENSOR_WIND_SPEED: "m/s",
    SENSOR_WIND_GUST: "m/s",
    SENSOR_WIND_DIRECTION: "°",
    SENSOR_RAIN: "mm/h",
    SENSOR_AIR_PRESSURE: "hPa",
}

# --- Climate modes ---
# dS OperationMode values
CLIMATE_OFF = 0
CLIMATE_COMFORT = 1
CLIMATE_ECONOMY = 2
CLIMATE_NOT_USED = 3
CLIMATE_NIGHT = 4
CLIMATE_HOLIDAY = 5

# --- Polling intervals (seconds) ---
POLL_INTERVAL = 30               # 30s for all sensor data
POLL_INTERVAL_ENERGY = 30        # kept for backwards compat
POLL_INTERVAL_TEMPERATURE = 300  # 5 min for temp control values
# Binary-input fallback poll. Motion/contact/door changes already arrive in
# real time via the stateChange event long-poll (_process_event); this loop is
# only a reconciliation vangnet for events missed during a reconnect. It runs a
# FULL apartment/getDevices each cycle, so it is the dominant steady-state dSS
# request stream — one every 5s was ~17k calls/day and slowed the dSS on larger
# installs (René, 25 aug 2026). Default relaxed to 30s (matches the main cycle);
# events keep the fast path instant. User-tunable via the integration options.
POLL_INTERVAL_BINARY = 30        # fallback reconcile for binary inputs

# Vangnet-cadans voor de twee zwaarste per-cyclus-blokken: de Joker-ACTOR
# live-confirm (getState + getOutputValue per actor, tot ~2×N calls) en de
# per-zone climate-status-poll (getTemperatureControlStatus per zone, ~N calls).
# BEIDE zijn puur vangnet — callScene-/stateChange-events houden switch en
# klimaatstatus tussendoor live. Ze hoeven dus niet elke 30s-hoofdcyclus mee;
# 1×/min is ruim voldoende en halveert hun dSS-last op grotere installs
# (René, 26 aug 2026). Op de default 30s-hoofdpoll valt dit op elke twééde cyclus.
POLL_INTERVAL_VANGNET = 60       # joker-actor confirm + climate-status vangnet

# Bounds for the user-configurable poll intervals (Options flow).
MIN_POLL_INTERVAL = 15
MAX_POLL_INTERVAL = 300
DEFAULT_MAIN_POLL_INTERVAL = POLL_INTERVAL_ENERGY   # 30s
DEFAULT_BINARY_POLL_INTERVAL = POLL_INTERVAL_BINARY  # 30s

# --- Event listener ---
EVENT_POLL_TIMEOUT = 60  # Long-poll timeout for event/get
EVENT_SUBSCRIPTION_ID = 42  # Our subscription ID

# --- Reconnect backoff ---
RECONNECT_INITIAL = 5
RECONNECT_MAX = 60

# --- Config keys ---
CONF_CONNECTION_TYPE = "connection_type"
CONF_APP_TOKEN = "app_token"
CONF_CLOUD_URL = "cloud_url"
CONF_CLOUD_USER = "cloud_user"
CONF_CLOUD_PASS = "cloud_pass"
CONF_ENABLED_ZONES = "enabled_zones"
CONF_DSS_ID = "dss_id"

# Options
CONF_INVERT_COVER = "invert_cover_position"
CONF_PRO_LICENSE = "pro_license_key"
CONF_MAIN_POLL_INTERVAL = "main_poll_interval"
CONF_BINARY_POLL_INTERVAL = "binary_poll_interval"
# Opt-in whitelist: dsuids of UMR200 outputs that drive a ventilation unit but
# are configured outside the dS Ventilation colour group (e.g. as Joker/black).
# These are treated as ventilation outputs regardless of their colour group.
# CSV of dsuids. Empty by default → strict GROUP_VENTILATION gate stays in force.
# René (28 aug 2026): his "Overloop Ventilatie" UMR200 outputs are Joker-config.
CONF_EXTRA_VENTILATION_DSUIDS = "extra_ventilation_dsuids"

# --- Platforms ---
# Free platforms (always loaded)
PLATFORMS_FREE = ["light", "cover", "sensor", "scene", "switch", "binary_sensor", "button", "event"]

# Pro platforms (requires license)
PLATFORMS_PRO = ["climate", "select"]

# All platforms
PLATFORMS = PLATFORMS_FREE + PLATFORMS_PRO


# --- Button / rocker press events (event platform) ---
# dSS functionIDs identifying pushbutton / rocker devices that emit `buttonClick`
# events. 33030 = EnOcean rocker switch (F6-02-FF). `buttonInputs` is not
# reliably populated for bridged plan44/EnOcean rockers, so we key off functionID.
BUTTON_FUNCTION_IDS = {33030}

# dSS clickType -> readable HA event-type suffix.
BUTTON_CLICK_TYPE_NAMES = {
    0: "single", 1: "double", 2: "triple", 3: "quadruple",
    4: "hold", 5: "hold_repeat", 6: "hold_release",
    7: "single", 8: "double", 9: "triple",
    10: "short_long", 11: "local_off", 12: "local_on",
    13: "short_short_long", 14: "local_stop",
}
# dSS buttonIndex (buttonElementID) -> readable HA event-type prefix.
BUTTON_ELEMENT_NAMES = {0: "button", 1: "down", 2: "up"}


def signal_button_event(entry_id: str) -> str:
    """Dispatcher signal carrying a dSS buttonClick for one config entry."""
    return f"{DOMAIN}_button_event_{entry_id}"

# --- User Defined States ---
# State source that marks an entry as a true User Defined Action (set in dSS Configurator)
USER_ACTION_SOURCE = "system-addon-user-defined-actions"

# System-level state names already exposed elsewhere — never import as User State
SKIP_USER_STATES = {
    "rain",          # already exposed as binary_sensor.dss_rain / weather protection
    "wind",          # handled per-device by dSS
    "frost",
    "fire",
    "fireMuteEnabled",
    "alarm", "alarm2", "alarm3", "alarm4",
    "panic",
    "presence",      # exposed via select.presence_mode (Pro)
    "hibernation",
}

# State value mapping: dSS internally encodes "active"=1, "inactive"=2 for binary states
STATE_VALUE_ACTIVE = 1
STATE_VALUE_INACTIVE = 2
