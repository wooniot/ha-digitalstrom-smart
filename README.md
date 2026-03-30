# Digital Strom Smart for Home Assistant

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/wooniot/ha-digitalstrom-smart)](https://github.com/wooniot/ha-digitalstrom-smart/releases)

A zone-based, event-driven Home Assistant integration for **Digital Strom** home automation systems. Built by [Woon IoT BV](https://wooniot.nl) — Digital Strom installation specialists.

> English | **[Deutsch](README.de.md)**

## Requirements

- **Digital Strom Server**: dSS20 or newer (firmware 1.19.x+)
- **Home Assistant**: 2024.1.0 or newer
- **Connection**: Local network access to your dSS (HTTPS, default port 8080)

> This integration connects directly to your dSS over your local network. No cloud connection or digitalstrom.net account required.

## Why this integration?

Unlike traditional per-device polling integrations, Digital Strom Smart uses the **scene-based architecture** that Digital Strom was designed for:

| | Traditional approach | Digital Strom Smart |
|--|---------------------|-------------------|
| **Control method** | Individual device commands | Zone scenes (one command, all devices respond) |
| **State updates** | Polling every 10-30s per device | Real-time event subscription |
| **Bus load** | ~50+ requests/min (10 zones) | ~0.4 requests/min + 1 event connection |
| **Risk** | Can corrupt apartments.xml | Safe — uses only standard API calls |

## Features

### Free

- **Zone-based lights** with brightness control (dimming via `setValue`)
- **Zone-based covers** (blinds/shades) with position control and direction inversion
- **Individual Joker switches** — each Joker actuator gets its own switch entity with the device name from dS Configurator
- **Joker binary sensors** — contact sensors, smoke detectors, door contacts are auto-detected as binary sensors with the correct device class
- **Scene activation** with imported dS scene names (the recommended way to control Digital Strom)
- **Temperature sensors** per zone (including rooms without heating, using any available source: zone sensors, device sensors)
- **Device sensors** — Ulux and similar devices expose CO2, brightness, temperature, and humidity as individual sensor entities
- **Energy monitoring** (apartment-level power consumption)
- **Per-circuit energy monitoring** — power consumption per dSM meter, each as its own device
- **Event-driven** — instant state updates when someone uses a wall switch
- **Scenes for all groups** — Light, Shade, and Heating scenes

### Pro

Unlock advanced features with a Pro license key from [wooniot.nl/pro](https://wooniot.nl/pro):

- **Climate control** — target temperature, preset modes (Comfort, Economy, Night, Holiday), heating + cooling detection
- **Outdoor weather sensors** — temperature, humidity, brightness, wind speed, wind gust, air pressure
- **Rain detection** — real-time rain sensor via dSS system-protection state events
- **Device identification** — blink any device for identification
- **Save scenes** — save current output values as a new scene
- **Area scenes** — full scene range support (6-9, 10-14, 20-24, 30-34, 40-44) plus all user-defined scenes from dSS

#### Pro license

Enter your Pro license key in the integration options (**Settings > Devices & Services > Digital Strom Smart > Configure**). License types:

| Type | Duration | Price |
|------|----------|-------|
| Trial | 30 days | Free (request via [wooniot.nl/pro](https://wooniot.nl/pro)) |
| Yearly | 365 days | €29/year |
| Lifetime | Permanent | €89 one-time |

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu (⋮) in the top right corner
3. Select **Custom repositories**
4. Add this URL: `https://github.com/wooniot/ha-digitalstrom-smart`
5. Category: **Integration**
6. Click **Add**
7. Now search for "Digital Strom Smart" and click Install
8. Restart Home Assistant

### Manual

1. Download the latest release from [GitHub](https://github.com/wooniot/ha-digitalstrom-smart/releases)
2. Copy `custom_components/digitalstrom_smart/` to your HA config directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for **Digital Strom**
3. Enter the **IP address** and **port** (default 8080) of your dSS
4. Approve the connection in your dSS admin interface:
   - Open the dSS web interface in your browser
   - Go to **System > Access Authorization**
   - Find **WoonIoT HA Connect** and check the box to approve
5. Click Submit — the integration discovers all zones and devices automatically

### Options

After setup, go to the integration options to:
- **Select zones** to include in Home Assistant
- **Invert cover direction** if blinds/screens move the wrong way
- **Enter Pro license key** to unlock advanced features

## Entities created

For each zone with devices:
- `light.<zone>_light` — Zone light control (on/off/brightness)
- `cover.<zone>_cover` — Zone cover control (open/close/position)
- `scene.<zone>_<scene_name>` — Activate dS presets (with user-defined names from dS)
- `sensor.<zone>_temperature` — Zone temperature (from any available source)

Individual Joker devices:
- `switch.<zone>_<device_name>` — Per-device on/off control (actuators with outputMode > 0)
- `binary_sensor.<zone>_<device_name>` — Contact/smoke/door sensors (devices with outputMode == 0)

Device-level sensors (Ulux, etc.):
- `sensor.<zone>_<device>_temperature` — Device temperature
- `sensor.<zone>_<device>_humidity` — Device humidity
- `sensor.<zone>_<device>_co2` — Device CO2 level
- `sensor.<zone>_<device>_brightness` — Device brightness

Apartment-level:
- `sensor.dss_power_consumption` — Total power (Watts)
- `sensor.dss_license_status` — License status: Pro/Free with validation details (diagnostic)

Per-circuit (dSM meters):
- `sensor.<circuit_name>_power` — Power per dSM meter (each meter is its own device)

Pro entities (requires license):
- `climate.<zone>_climate` — Zone climate control with target temperature
- `sensor.dss_outdoor_*` — Outdoor weather sensors
- `binary_sensor.dss_rain` — Rain detection

## Services

| Service | Description | Pro |
|---------|-------------|-----|
| `digitalstrom_smart.call_scene` | Activate a scene (zone_id, group, scene_number) | |
| `digitalstrom_smart.blink_device` | Blink a device for identification (dsuid) | Yes |
| `digitalstrom_smart.save_scene` | Save current output values as a scene | Yes |

## Climate notes

### Passive cooling
Digital Strom uses **passive cooling** — the dSS does not actively control cooling output. When the system switches to cooling mode:
- The climate entity shows **Cooling** in Home Assistant
- Adjusting the target temperature will briefly show the entity as **Idle** — this is normal
- The switch back to heating takes 1-2 minutes (controlled by the dSS)
- The minimum setpoint configured in the dSS applies during cooling mode

## Architecture

```
Home Assistant
  │
  └── Digital Strom Smart
        │
        ├── Event Listener (long-poll)
        │     ├── callScene / undoScene → Light, Cover, Switch, Scene state
        │     ├── zoneSensorValue → Temperature sensors
        │     ├── deviceSensorValue → Device sensors (Ulux CO2/Lux/Temp)
        │     ├── stateChange → Binary sensors (contacts, smoke, door)
        │     └── stateChange → Rain detection (apartment-level)
        │
        ├── Binary Input Polling (every 5s)
        │     └── apartment/getDevices → Contact/door/window state
        │
        ├── Polling (every 30s)
        │     ├── getConsumption → Energy sensor
        │     ├── getTemperatureControlValues → Zone temperatures
        │     └── PRO: getSensorValues, getCircuits, climate status
        │
        └── Commands
              ├── callScene / setValue → Zone lights, covers, scenes
              └── device/turnOn / turnOff → Individual Joker switches
```

## Supported hardware

- **dSS20** (minimum) or newer Digital Strom Server
- All Digital Strom device types: GE (light), GR (shade), SW (joker/black), BL (blinds)
- Joker actuators (relays, switches) — individually controllable
- Joker sensors (contacts, smoke detectors, door sensors) — auto-detected device class
- Ulux and similar multi-sensor devices (CO2, brightness, temperature, humidity)
- dSM meters (energy monitoring)
- Outdoor weather stations (temperature, humidity, brightness, wind speed/gust, pressure)
- Rain detection via dSS system-protection state
- Climate control zones (heating and cooling)

## Translations

Digital Strom Smart supports multiple languages for all entity names, configuration screens, and state values:

| Language | Status |
|----------|--------|
| English | Complete |
| Nederlands (Dutch) | Complete |
| Deutsch (German) | Complete |

Home Assistant automatically uses the correct language based on your system language setting. Want to add a translation? PRs welcome — just create a new JSON file in `custom_components/digitalstrom_smart/translations/`.

## Changelog

### v2.9.2 (2026-03-30)
- **License diagnostics sensor** — shows Pro/Free status with attributes: valid, reason, dss_id_sent, validation_method
- **Pro validation logging** — warning in HA logs when license validation fails (with reason)
- No more guessing why Pro features are inactive — check the sensor or HA logs

### v2.9.0 (2026-03-29)
- **Full i18n** — all entity names now translatable via Home Assistant's native translation system
- **German translation** — complete DE translation for all entities, config flow, and options
- **Dutch translation** — complete NL translation for all entities
- Translated: sensors, lights, covers, climate, switches, presence mode (with state values), binary sensors, scenes (including area scenes)
- **Breaking change**: Presence Mode select options changed from display names (`"Present"`, `"Absent"`) to internal keys (`"present"`, `"absent"`). Update automations using `select.select_option` accordingly.

### v2.8.7 (2026-03-24)
- **Binary sensor debug logging** — improved diagnostic logging for Joker binary sensors

### v2.8.6 (2026-03-20)
- **Binary sensor fix** — contact sensors (doors, windows, UMR, EnOcean) now report correct open/closed state
- **Fast binary polling** — separate 5-second polling loop for contact/door/window sensors (was 30s)
- **Correct API** — uses `apartment/getDevices` for binary input state (reliable across all dSS firmware versions)
- **Polarity fix** — contact-type sensors correctly inverted (dSS "active"=closed, HA on=open). Motion/presence unchanged.
- **Area scenes** (Pro) — support for scenes 6-9, 10-14, 20-24, 30-34, 40-44
- **Dynamic scene discovery** (Pro) — automatically creates entities for all reachable and named scenes from dSS

### v2.8.0 (2026-03-17)
- **Cooling mode detection via event** — uses `heating_system_mode` stateChange event (active=heating, inactive=cooling) as the primary cooling detection method
- When dSS switches to cooling, the heating controller API returns only `{ControlMode: 0}` with no cooling indicator — the real signal is the apartment-level event
- Cooling check runs before off-detection in both `hvac_mode` and `hvac_action`
- Passive cooling behavior documented (see Climate notes)

### v2.7.4 (2026-03-17)
- **Rain sensor fix** — detects apartment-level stateChange events (StateApartment;rain)
- **Wind Protection removed** — dSS handles wind protection per device internally, no universal state exists
- **Climate detection fix** — now detects climate zones regardless of ControlMode format (string or integer)
- **Cooling mode fix** — robust type handling for ControlMode/OperationMode values from dSS API

### v2.6.1 (2026-03-15)
- **Weather protection** as binary sensors (rain detection via dSS system-protection)
- **Climate entity improvements** — better detection for PLAN44/EnOcean setups

### v2.5.0 (2026-03-14)
- **Alarm entities** — alarm 1-4, panic, doorbell as switch entities
- **Presence detection** — present, absent, sleeping, wakeup, standby, deep off

### v2.4.0 (2026-03-13)
- **Per-dSM energy monitoring** moved to Free tier — each dSM meter gets its own device with power sensor
- **Sensor reliability** — uses dSS zone API for pre-scaled values, removed all manual bus-encoding
- Automatic dSM filtering (virtual controllers excluded)
- Sensor values now always match what the dSS reports, regardless of device type

### v2.2.0 (2026-03-11)
- **Free/Pro tier split** with license key system ([wooniot.nl/pro](https://wooniot.nl/pro))
- **Individual Joker switches** — per-device control with names from dS Configurator
- **Joker binary sensors** — contact, smoke, door sensors with auto-detected device class
- **Device sensors** — Ulux CO2, brightness, temperature, humidity as individual entities
- **Climate control** (Pro) — target temperature, presets, heating + cooling detection
- **Outdoor weather sensors** (Pro) — temperature, humidity, brightness, wind, pressure, rain
- **Scene discovery** with user-defined names from dS Configurator
- Temperature for rooms without heating (any available source)

### v1.0.0 (2026-03-10)
- Initial release: zone-based lights, covers, scenes, temperature sensors, energy monitoring
- Event-driven architecture with real-time state updates
- Local and cloud connection support

## About

Developed by **[Woon IoT BV](https://wooniot.nl)** — professional Digital Strom installers and smart home specialists based in the Netherlands.

- Website: [wooniot.nl](https://wooniot.nl)
- Pro license: [wooniot.nl/pro](https://wooniot.nl/pro)
- Issues: [GitHub Issues](https://github.com/wooniot/ha-digitalstrom-smart/issues)
- License: MIT
