"""Constants for digitalSTROM Smart integration by Woon IoT BV."""

DOMAIN = "digitalstrom_smart"
MANUFACTURER = "digitalSTROM"
INTEGRATION_AUTHOR = "Woon IoT BV"
INTEGRATION_URL = "https://github.com/wooniot/ha-digitalstrom-smart"
INTEGRATION_VERSION = "1.0.0"

# Application name shown in dSS Configurator under registered applications
DSS_APP_NAME = "WoonIoT HA Connect"

# Telemetry endpoint (opt-in, anonymous)
TELEMETRY_URL = "https://ha-ds.internetist.nl/ha-ds/ping"

# Connection types
CONN_LOCAL = "local"
CONN_CLOUD = "cloud"

# dS Group IDs
GROUP_LIGHT = 1
GROUP_SHADE = 2
GROUP_HEATING = 3
GROUP_AUDIO = 4
GROUP_VIDEO = 5
GROUP_SECURITY = 6
GROUP_ACCESS = 7
GROUP_JOKER = 8  # Black devices (switches, etc.)

GROUP_NAMES = {
    GROUP_LIGHT: "Light",
    GROUP_SHADE: "Shade",
    GROUP_HEATING: "Heating",
    GROUP_AUDIO: "Audio",
    GROUP_VIDEO: "Video",
    GROUP_SECURITY: "Security",
    GROUP_ACCESS: "Access",
    GROUP_JOKER: "Joker",
}

# dS Scene Numbers
SCENE_OFF = 0
SCENE_1 = 5       # Preset 1 (usually "on" / max)
SCENE_2 = 17      # Preset 2
SCENE_3 = 18      # Preset 3
SCENE_4 = 19      # Preset 4
SCENE_MAX = 5     # Same as Scene 1
SCENE_MIN = 0     # Off

# Cover scenes
SCENE_COVER_OPEN = 5    # Up / Open
SCENE_COVER_CLOSE = 0   # Down / Close
SCENE_COVER_STOP = 15   # Stop

NAMED_SCENES = {
    SCENE_OFF: "Off",
    SCENE_1: "Scene 1",
    SCENE_2: "Scene 2",
    SCENE_3: "Scene 3",
    SCENE_4: "Scene 4",
}

# Cover scenes (GROUP_SHADE)
NAMED_SCENES_SHADE = {
    SCENE_OFF: "Shade Down",
    SCENE_1: "Shade Preset 1",
    SCENE_2: "Shade Preset 2",
    SCENE_3: "Shade Preset 3",
    SCENE_4: "Shade Preset 4",
}

# Climate/Heating scenes (GROUP_HEATING)
GROUP_HEATING_SCENES = {
    SCENE_OFF: "Comfort Off",
    SCENE_1: "Comfort",
    SCENE_2: "Economy",
    SCENE_3: "Night",
    SCENE_4: "Holiday",
}

# Scene number to name lookup from dS getStructure per zone group
# (populated at runtime from dSS data)

# Polling intervals (seconds)
POLL_INTERVAL_ENERGY = 300       # 5 min for consumption
POLL_INTERVAL_TEMPERATURE = 300  # 5 min for temp control values

# Event listener
EVENT_POLL_TIMEOUT = 60  # Long-poll timeout for event/get
EVENT_SUBSCRIPTION_ID = 42  # Our subscription ID

# Reconnect backoff
RECONNECT_INITIAL = 5
RECONNECT_MAX = 60

# Config keys
CONF_CONNECTION_TYPE = "connection_type"
CONF_APP_TOKEN = "app_token"
CONF_CLOUD_URL = "cloud_url"
CONF_CLOUD_USER = "cloud_user"
CONF_CLOUD_PASS = "cloud_pass"
CONF_ENABLED_ZONES = "enabled_zones"
CONF_DSS_ID = "dss_id"

# Config keys for options
CONF_INVERT_COVER = "invert_cover_position"

# Platforms
PLATFORMS = ["light", "cover", "sensor", "scene", "switch"]
