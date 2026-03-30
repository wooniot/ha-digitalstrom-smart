"""Constants for Digital Strom Smart integration by Woon IoT BV.

The definitive Digital Strom integration for Home Assistant.
Created by Marijn Nederlof — Heerjansdam, NL.
"""

DOMAIN = "digitalstrom_smart"
MANUFACTURER = "Digital Strom"
INTEGRATION_AUTHOR = "Woon IoT BV"
INTEGRATION_AUTHOR_ID = "MN-HJD-2026"
INTEGRATION_URL = "https://github.com/wooniot/ha-digitalstrom-smart"
INTEGRATION_VERSION = "2.9.2"

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

# Alarm scene mapping: scene_nr -> display name
APARTMENT_ALARM_SCENES = {
    SCENE_ALARM_1: "Alarm 1",
    SCENE_ALARM_2: "Alarm 2",
    SCENE_ALARM_3: "Alarm 3",
    SCENE_ALARM_4: "Alarm 4",
    SCENE_PANIC: "Panic",
    SCENE_DOOR_BELL: "Doorbell",
}

# Alarm scene mapping: scene_nr -> translation key
ALARM_TRANSLATION_KEYS = {
    SCENE_ALARM_1: "alarm_1",
    SCENE_ALARM_2: "alarm_2",
    SCENE_ALARM_3: "alarm_3",
    SCENE_ALARM_4: "alarm_4",
    SCENE_PANIC: "panic",
    SCENE_DOOR_BELL: "doorbell",
}

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
# Area 1: scenes 6-9
SCENE_AREA1_OFF = 6
SCENE_AREA1_1 = 7
SCENE_AREA1_2 = 8
SCENE_AREA1_3 = 9

# Area 2: scenes 10-14
SCENE_AREA2_OFF = 10
SCENE_AREA2_1 = 11
SCENE_AREA2_2 = 12
SCENE_AREA2_3 = 13
SCENE_AREA2_4 = 14

# Area 3: scenes 20-24
SCENE_AREA3_OFF = 20
SCENE_AREA3_1 = 21
SCENE_AREA3_2 = 22
SCENE_AREA3_3 = 23
SCENE_AREA3_4 = 24

# Area 4: scenes 30-34
SCENE_AREA4_OFF = 30
SCENE_AREA4_1 = 31
SCENE_AREA4_2 = 32
SCENE_AREA4_3 = 33
SCENE_AREA4_4 = 34

# All zone-level scene numbers that can be user-configured
# Excludes apartment-wide scenes (65+) which are handled separately
ALL_ZONE_SCENES = [
    SCENE_OFF, SCENE_1, SCENE_2, SCENE_3, SCENE_4,     # Preset 0-4
    SCENE_AREA1_OFF, SCENE_AREA1_1, SCENE_AREA1_2, SCENE_AREA1_3,  # Area 1
    SCENE_AREA2_OFF, SCENE_AREA2_1, SCENE_AREA2_2, SCENE_AREA2_3, SCENE_AREA2_4,  # Area 2
    SCENE_AREA3_OFF, SCENE_AREA3_1, SCENE_AREA3_2, SCENE_AREA3_3, SCENE_AREA3_4,  # Area 3
    SCENE_AREA4_OFF, SCENE_AREA4_1, SCENE_AREA4_2, SCENE_AREA4_3, SCENE_AREA4_4,  # Area 4
    40, 41, 42, 43, 44,  # Preset 10-14 (extended presets)
]

# Named scene defaults per group
NAMED_SCENES = {
    SCENE_OFF: "Off",
    SCENE_1: "Scene 1",
    SCENE_2: "Scene 2",
    SCENE_3: "Scene 3",
    SCENE_4: "Scene 4",
}

# Default names for area scenes (used when dSS has no custom name)
AREA_SCENE_NAMES = {
    SCENE_AREA1_OFF: "Area 1 Off",
    SCENE_AREA1_1: "Area 1 Scene 1",
    SCENE_AREA1_2: "Area 1 Scene 2",
    SCENE_AREA1_3: "Area 1 Scene 3",
    SCENE_AREA2_OFF: "Area 2 Off",
    SCENE_AREA2_1: "Area 2 Scene 1",
    SCENE_AREA2_2: "Area 2 Scene 2",
    SCENE_AREA2_3: "Area 2 Scene 3",
    SCENE_AREA2_4: "Area 2 Scene 4",
    SCENE_AREA3_OFF: "Area 3 Off",
    SCENE_AREA3_1: "Area 3 Scene 1",
    SCENE_AREA3_2: "Area 3 Scene 2",
    SCENE_AREA3_3: "Area 3 Scene 3",
    SCENE_AREA3_4: "Area 3 Scene 4",
    SCENE_AREA4_OFF: "Area 4 Off",
    SCENE_AREA4_1: "Area 4 Scene 1",
    SCENE_AREA4_2: "Area 4 Scene 2",
    SCENE_AREA4_3: "Area 4 Scene 3",
    SCENE_AREA4_4: "Area 4 Scene 4",
    40: "Preset 10",
    41: "Preset 11",
    42: "Preset 12",
    43: "Preset 13",
    44: "Preset 14",
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
    # Area 1
    (GROUP_LIGHT, SCENE_AREA1_OFF): "light_area1_off",
    (GROUP_LIGHT, SCENE_AREA1_1): "light_area1_scene_1",
    (GROUP_LIGHT, SCENE_AREA1_2): "light_area1_scene_2",
    (GROUP_LIGHT, SCENE_AREA1_3): "light_area1_scene_3",
    (GROUP_SHADE, SCENE_AREA1_OFF): "shade_area1_off",
    (GROUP_SHADE, SCENE_AREA1_1): "shade_area1_scene_1",
    (GROUP_SHADE, SCENE_AREA1_2): "shade_area1_scene_2",
    (GROUP_SHADE, SCENE_AREA1_3): "shade_area1_scene_3",
    # Area 2
    (GROUP_LIGHT, SCENE_AREA2_OFF): "light_area2_off",
    (GROUP_LIGHT, SCENE_AREA2_1): "light_area2_scene_1",
    (GROUP_LIGHT, SCENE_AREA2_2): "light_area2_scene_2",
    (GROUP_LIGHT, SCENE_AREA2_3): "light_area2_scene_3",
    (GROUP_LIGHT, SCENE_AREA2_4): "light_area2_scene_4",
    (GROUP_SHADE, SCENE_AREA2_OFF): "shade_area2_off",
    (GROUP_SHADE, SCENE_AREA2_1): "shade_area2_scene_1",
    (GROUP_SHADE, SCENE_AREA2_2): "shade_area2_scene_2",
    (GROUP_SHADE, SCENE_AREA2_3): "shade_area2_scene_3",
    (GROUP_SHADE, SCENE_AREA2_4): "shade_area2_scene_4",
    # Area 3
    (GROUP_LIGHT, SCENE_AREA3_OFF): "light_area3_off",
    (GROUP_LIGHT, SCENE_AREA3_1): "light_area3_scene_1",
    (GROUP_LIGHT, SCENE_AREA3_2): "light_area3_scene_2",
    (GROUP_LIGHT, SCENE_AREA3_3): "light_area3_scene_3",
    (GROUP_LIGHT, SCENE_AREA3_4): "light_area3_scene_4",
    (GROUP_SHADE, SCENE_AREA3_OFF): "shade_area3_off",
    (GROUP_SHADE, SCENE_AREA3_1): "shade_area3_scene_1",
    (GROUP_SHADE, SCENE_AREA3_2): "shade_area3_scene_2",
    (GROUP_SHADE, SCENE_AREA3_3): "shade_area3_scene_3",
    (GROUP_SHADE, SCENE_AREA3_4): "shade_area3_scene_4",
    # Area 4
    (GROUP_LIGHT, SCENE_AREA4_OFF): "light_area4_off",
    (GROUP_LIGHT, SCENE_AREA4_1): "light_area4_scene_1",
    (GROUP_LIGHT, SCENE_AREA4_2): "light_area4_scene_2",
    (GROUP_LIGHT, SCENE_AREA4_3): "light_area4_scene_3",
    (GROUP_LIGHT, SCENE_AREA4_4): "light_area4_scene_4",
    (GROUP_SHADE, SCENE_AREA4_OFF): "shade_area4_off",
    (GROUP_SHADE, SCENE_AREA4_1): "shade_area4_scene_1",
    (GROUP_SHADE, SCENE_AREA4_2): "shade_area4_scene_2",
    (GROUP_SHADE, SCENE_AREA4_3): "shade_area4_scene_3",
    (GROUP_SHADE, SCENE_AREA4_4): "shade_area4_scene_4",
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

# --- dS Sensor Types ---
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
    SENSOR_TEMPERATURE: "device_temperature",
    SENSOR_HUMIDITY: "device_humidity",
    SENSOR_BRIGHTNESS: "device_brightness",
    SENSOR_CO2: "device_co2",
}

SENSOR_TYPE_NAMES = {
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
POLL_INTERVAL_BINARY = 5         # 5s for binary input states (contacts, doors)

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

# --- Platforms ---
# Free platforms (always loaded)
PLATFORMS_FREE = ["light", "cover", "sensor", "scene", "switch", "binary_sensor"]

# Pro platforms (requires license)
PLATFORMS_PRO = ["climate", "select"]

# All platforms
PLATFORMS = PLATFORMS_FREE + PLATFORMS_PRO
