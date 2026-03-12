"""Constants for Digital Strom Smart integration by Woon IoT BV.

The definitive Digital Strom integration for Home Assistant.
"""

DOMAIN = "digitalstrom_smart"
MANUFACTURER = "Digital Strom"
INTEGRATION_AUTHOR = "Woon IoT BV"
INTEGRATION_URL = "https://github.com/wooniot/ha-digitalstrom-smart"
INTEGRATION_VERSION = "2.2.8"

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

# Apartment-wide scenes
SCENE_DEEP_OFF = 68
SCENE_STANDBY = 67
SCENE_PANIC = 65
SCENE_ALARM = 74
SCENE_FIRE = 76
SCENE_WIND = 71
SCENE_RAIN = 73

# Cover scenes
SCENE_COVER_OPEN = 5    # Up / Open
SCENE_COVER_CLOSE = 0   # Down / Close
SCENE_COVER_STOP = 15   # Stop
SCENE_COVER_SUN_PROTECT = 11  # Sun protection position
SCENE_COVER_WIND_PROTECT = 71  # Wind protection (fully open)

# Named scene defaults per group
NAMED_SCENES = {
    SCENE_OFF: "Off",
    SCENE_1: "Scene 1",
    SCENE_2: "Scene 2",
    SCENE_3: "Scene 3",
    SCENE_4: "Scene 4",
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
POLL_INTERVAL_ENERGY = 300       # 5 min for consumption
POLL_INTERVAL_TEMPERATURE = 300  # 5 min for temp control values

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
PLATFORMS_PRO = ["climate"]

# All platforms
PLATFORMS = PLATFORMS_FREE + PLATFORMS_PRO
