# Digital Strom Smart for Home Assistant

[![HACS Badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
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
- **Event-driven** — instant state updates when someone uses a wall switch
- **Scenes for all groups** — Light, Shade, and Heating scenes

### Pro

Unlock advanced features with a Pro license key from [wooniot.nl/pro](https://wooniot.nl/pro):

- **Climate control** — target temperature, preset modes (Comfort, Economy, Night, Holiday), heating + cooling detection
- **Outdoor weather sensors** — temperature, humidity, brightness, wind, air pressure, rain detection
- **Per-circuit energy monitoring** — power consumption per dSM meter
- **Device identification** — blink any device for identification
- **Save scenes** — save current output values as a new scene

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
2. Search for "Digital Strom Smart"
3. Click Install
4. Restart Home Assistant

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

Pro entities (requires license):
- `climate.<zone>_climate` — Zone climate control with target temperature
- `sensor.dss_outdoor_*` — Outdoor weather sensors
- `sensor.dss_circuit_*_power` — Per-circuit power consumption
- `binary_sensor.dss_rain` — Rain detection

## Services

| Service | Description | Pro |
|---------|-------------|-----|
| `digitalstrom_smart.call_scene` | Activate a scene (zone_id, group, scene_number) | |
| `digitalstrom_smart.blink_device` | Blink a device for identification (dsuid) | Yes |
| `digitalstrom_smart.save_scene` | Save current output values as a scene | Yes |

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
        │     └── stateChange → Binary sensors (contacts, smoke, door)
        │
        ├── Polling (every 5 min)
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
- Outdoor weather stations (temperature, humidity, brightness, wind, pressure, rain)
- Climate control zones (heating and cooling)

## Changelog

### v2.3.1 (2026-03-13)
- Use pre-scaled sensor values from dSS structure data instead of raw getSensorValue API calls
- The dSS already handles all bus-encoding conversions — no manual scaling needed
- Removes fragile device-specific scaling logic (raw/40, raw/100, etc.)
- Sensor values now always match what the dSS reports, regardless of device type

### v2.3.0 (2026-03-12)
- Fix dS-bus sensor scaling: use official dS bus 12-bit encoding per sensor type
- Temperature: `raw / 40 - 43.2`, Humidity: `raw / 40` (not raw/100)
- Verified against dSS zone API values — now matches exactly
- Fixes wrong humidity (showed ~22% instead of ~56%) and temperature offsets on dS-bus devices

### v2.2.9 (2026-03-12)
- Fix sensor scaling: use dSUID prefix to reliably detect dS-bus devices (always raw /100) vs EnOcean devices (already float)
- Fixes incorrect brightness and CO2 values (e.g., 2149 lx shown instead of 21.49 lx)
- Removes unreliable range-based heuristic in favor of deterministic dSUID prefix check

### v2.2.8 (2026-03-12)
- Fix device sensor scaling: smart detection of raw integer vs float values from dSS API
- EnOcean sensors (Thermokon) return proper floats, dS-bus sensors (FTW04, TNY210) return raw integers — both now handled correctly
- FTW04 temperature/humidity sensors now display correct values
- Ulux/TNY210 CO2, brightness, temperature, humidity sensors supported
- Improved startup logging for device sensor discovery

### v2.2.5 (2026-03-12)
- Joker actuators (outputMode > 0) now create **switch** entities
- Joker sensors (outputMode == 0) now create **binary_sensor** entities with auto-detected device class (door, window, smoke, motion, etc.)
- binary_sensor platform moved to Free tier

### v2.2.4 (2026-03-12)
- Fix sensor values displayed 100x too high (use `sensorValueFloat` from dSS events)

### v2.2.3 (2026-03-12)
- Individual Joker device switches with names from dS Configurator
- Device-level control via `/json/device/turnOn` and `/json/device/turnOff`

### v2.2.0 (2026-03-11)
- Ulux device sensors (CO2, brightness, temperature, humidity)
- Climate cooling detection (HVACMode.COOL)
- Temperature for rooms without heating (any available source)
- Joker (group 8) support
- Rain sensor from outdoor weather station
- Removed Pause/Resume (no longer needed)
- Telemetry reliability improvements

### v2.0.0 (2026-03-10)
- Free/Pro tier split with license key system
- Climate control (Pro)
- Outdoor weather sensors (Pro)
- Per-circuit energy monitoring (Pro)
- Scene discovery with user-defined names

### v1.0.0
- Initial release: lights, covers, scenes, sensors, energy

## About

Developed by **[Woon IoT BV](https://wooniot.nl)** — professional Digital Strom installers and smart home specialists based in the Netherlands.

- Website: [wooniot.nl](https://wooniot.nl)
- Pro license: [wooniot.nl/pro](https://wooniot.nl/pro)
- Issues: [GitHub Issues](https://github.com/wooniot/ha-digitalstrom-smart/issues)
- License: MIT
