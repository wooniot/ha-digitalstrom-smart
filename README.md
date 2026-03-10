# Digital Strom Smart for Home Assistant

[![HACS Badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/wooniot/ha-digitalstrom-smart)](https://github.com/wooniot/ha-digitalstrom-smart/releases)

A zone-based, event-driven Home Assistant integration for **Digital Strom** home automation systems. Built by [Woon IoT BV](https://wooniot.nl) — Digital Strom installation specialists.

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

- **Zone-based lights** with brightness control
- **Zone-based covers** (blinds/shades) with position control and direction inversion
- **Scene activation** with imported dS scene names (the recommended way to control Digital Strom)
- **Temperature sensors** per zone
- **Energy monitoring** (apartment-level power consumption)
- **Pause/Resume** switch for safe dS Configurator use
- **Event-driven** — instant state updates when someone uses a wall switch
- **Scenes for all groups** — Light, Shade, and Heating scenes

### Pro

Unlock advanced features with a Pro license key from [wooniot.nl/pro](https://wooniot.nl/pro):

- **Climate control** — target temperature, preset modes (Comfort, Economy, Night, Holiday)
- **Outdoor weather sensors** — temperature, humidity, brightness, wind, air pressure
- **Per-circuit energy monitoring** — power consumption per dSM meter
- **Binary sensors** — Joker (black) device states
- **Device identification** — blink any device for identification
- **Save scenes** — save current output values as a new scene

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
- `sensor.<zone>_temperature` — Zone temperature

Apartment-level:
- `sensor.dss_power_consumption` — Total power (Watts)
- `switch.dss_pause_communication` — Pause for dS Configurator

Pro entities (requires license):
- `climate.<zone>_climate` — Zone climate control with target temperature
- `sensor.<zone>_outdoor_*` — Outdoor weather sensors
- `sensor.dss_circuit_*_power` — Per-circuit power consumption
- `binary_sensor.<zone>_*` — Joker device states

## Services

| Service | Description | Pro |
|---------|-------------|-----|
| `digitalstrom_smart.call_scene` | Activate a scene (zone_id, group, scene_number) | |
| `digitalstrom_smart.pause` | Pause all dSS communication | |
| `digitalstrom_smart.resume` | Resume communication | |
| `digitalstrom_smart.blink_device` | Blink a device for identification (dsuid) | Yes |
| `digitalstrom_smart.save_scene` | Save current output values as a scene | Yes |

## Using the Pause switch

When you need to use the **dS Configurator** to modify your installation:
1. Turn ON the Pause switch — all dSS communication stops
2. Use dS Configurator freely
3. Turn OFF the Pause switch — the integration reconnects and resyncs

## Architecture

```
Home Assistant
  │
  └── Digital Strom Smart
        │
        ├── Event Listener (long-poll)
        │     ├── callScene / undoScene → Light, Cover, Scene state
        │     ├── zoneSensorValue → Temperature sensors
        │     └── deviceSensorValue → Binary sensors (Pro)
        │
        ├── Polling (every 5 min)
        │     ├── getConsumption → Energy sensor
        │     └── getTemperatureControlValues → Climate (Pro)
        │
        └── Commands → callScene, setValue, turnOn, turnOff
              (one command per zone, not per device)
```

## Supported hardware

- **dSS20** (minimum) or newer Digital Strom Server
- All Digital Strom device types: GE (light), GR (shade), SW (joker/black), BL (blinds)
- dSM meters (energy monitoring)
- Temperature, humidity, brightness, wind, pressure sensors
- Climate control zones (heating/cooling)

## About

Developed by **[Woon IoT BV](https://wooniot.nl)** — professional Digital Strom installers and smart home specialists based in the Netherlands.

- Website: [wooniot.nl](https://wooniot.nl)
- Pro license: [wooniot.nl/pro](https://wooniot.nl/pro)
- Issues: [GitHub Issues](https://github.com/wooniot/ha-digitalstrom-smart/issues)
- License: MIT
