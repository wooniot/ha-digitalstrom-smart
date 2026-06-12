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
- **Apartment power monitoring** — apartment-level power consumption (W)
- **Alarm binary sensors** — Fire/Brand, Alarm 1-4, Panic, and Doorbell appear as binary sensors under the Digital Strom Server device, with live updates from dSS alarm events
- **System scene switches** — trigger Panic, Fire/Brand, Alarm 1-4 and Doorbell apartment-wide from HA as switches (via `apartment/callScene`); each switch reads the real dSS state back, so it returns to off by itself if the dSS ignores the scene
- **Environment states** — Day/Night, Twilight, Daylight and Holiday from the dSS as read-only binary sensors
- **Event-driven** — instant state updates when someone uses a wall switch
- **Scenes for all groups** — Light, Shade, and Heating scenes

### Pro

Unlock advanced features with a Pro license key from [wooniot.nl/pro](https://wooniot.nl/pro):

- **Climate control** — target temperature, preset modes (Comfort, Economy, Night, Holiday), heating + cooling detection
- **Presence mode** — read and set the apartment presence state (Present, Absent, Sleeping, …) as a select entity
- **User Defined Actions** — actions configured in the dSS Configurator appear as Home Assistant **buttons**
- **User Defined States** — custom and apartment-wide dSS states appear as **sensors / binary sensors** with live updates from `stateChange` events
- **Per-circuit (dSM) energy** — power **and** lifetime kWh per dSM meter, each as its own device, ready for the **HA Energy Dashboard**
- **Apartment kWh sensor** — aggregated cumulative energy across all dSMs (Energy Dashboard ready)
- **Motion per zone** — per-zone motion binary sensors from the dSS `zone.X.motion` states
- **Malfunction & service** — aggregate diagnostic binary sensors that flag any component reporting a malfunction or service-required
- **Outdoor weather sensors** — temperature, humidity, brightness, wind speed, wind gust, air pressure (weather station), plus a station-free outdoor temperature + sun position from the dSS weather service
- **Rain detection** — real-time rain sensor via dSS system-protection state events
- **Weather protection sensors** — wind/rain protection scene states as binary sensors
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

> **Note:** per-device power (W) and per-device energy (Wh) sensors were removed in v3.7.6. Reading them required polling the dSS sensor bus, which starved the dSM metering controller and corrupted the dSM energy values. Power and energy are now measured at the dSM (circuit) level only — see *Per-circuit (dSM) meters* below.

Apartment-level (Free):
- `sensor.dss_power_consumption` — Total power (Watts)
- `sensor.dss_license_status` — License status: Pro/Free with validation details (diagnostic)

Alarm & system states (Digital Strom Server device) — **Free**:
- `binary_sensor.dss_fire` — Fire alarm (Brand), device class: smoke
- `binary_sensor.dss_alarm_1` … `alarm_4` — Alarm states 1-4
- `binary_sensor.dss_panic` — Panic alarm
- `binary_sensor.dss_doorbell` — Doorbell active state
- `binary_sensor.dss_frost` / `hail` / `wind` / `rain` — Weather/protection states (read-only)
- `binary_sensor.dss_daynight` / `twilight` / `daylight` / `holiday` — Environment states (read-only)
- `switch.dss_fire`, `switch.dss_alarm_1` … `alarm_4`, `switch.dss_panic`, `switch.dss_doorbell` — Trigger the matching apartment scene via `apartment/callScene`. The switch mirrors the real dSS state, so it flips back to off by itself if the dSS ignores the scene

Per-circuit (dSM meters) — **Pro**:
- `sensor.<circuit_name>_power` — Instantaneous power per dSM meter (W)
- `sensor.<circuit_name>_energy` — Cumulative lifetime energy per dSM (kWh, `total_increasing`)
- `sensor.dss_energy_consumption` — Apartment-wide kWh, sum of all dSMs (Energy Dashboard ready)

User Defined Actions & States (apartment) — **Pro**:
- `button.<action_name>` — One button per action defined in the dSS Configurator
- `sensor.<state_name>` / `binary_sensor.<state_name>` — One entity per custom/apartment state, with live updates from dSS events

Other Pro entities (requires license):
- `climate.<zone>_climate` — Zone climate control with target temperature
- `select.<...>_presence` — Apartment presence mode (Present / Absent / Sleeping / …)
- `binary_sensor.<zone>_motion` — Per-zone motion (dSS `zone.X.motion` states)
- `binary_sensor.dss_malfunction` / `dss_service` — Aggregate malfunction / service-required (diagnostic)
- `sensor.dss_outdoor_*` — Outdoor weather-station sensors
- `sensor.dss_ws_outdoor_temperature` / sun position — Station-free outdoor data from the dSS weather service
- `binary_sensor.dss_rain` — Rain detection
- `binary_sensor.dss_*_protection` — Wind/rain weather-protection scene states

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

### v4.0.0 (2026-06-12) — System scenes, robust metering & environment states

- **System alarm scenes as switches** — Fire/Brand and Alarm 1-4 now get a switch (next to the read-only status binary sensor) that triggers the scene via `apartment/callScene`. Each switch reads the real dSS state back, so it returns to off by itself if the dSS ignores the scene.
- **Environment states (Free)** — Day/Night, Twilight, Daylight and Holiday exposed as read-only binary sensors.
- **Per-zone motion + malfunction/service (Pro)** — per-zone motion binary sensors, plus aggregate malfunction and service-required diagnostics.
- **Weather service (Pro)** — station-free outdoor temperature and sun position from the dSS weather service.
- **Metering rework** — per-device power (W) and energy (Wh) sensors were removed: polling the dSS sensor bus for them starved the dSM metering controller and corrupted the dSM energy values. Power and energy are now read at the dSM (circuit) level only. Per-device power is event-driven, never polled.
- **Reliability** — IP-change reconfigure + DHCP discovery, faster non-blocking startup, and a hardened event loop (one malformed event can no longer stop the loop). Apartment system states (fire/rain/frost/hail/wind/alarm) are read-only where the dSS rejects writes.

### v3.2.1 (2026-05-19) — Bug fixes

- **Fix**: Energy sensor (kWh) on Joker devices showing "unknown" at startup — now polled explicitly at first load
- **Fix**: Devices not assigned to HA area automatically — `suggested_area` added to all platform entities
- **Privacy**: Telemetry opt-out toggle added in integration options (Settings → Configure)
- Trial licenses require telemetry; paid Pro licenses work without it

### v3.1.0 (2026-05-18) — Per-device power measurement

- **New**: Power sensor entity (Watts) for SW-KL200, SW-ZWS200, SW-SSL200, SW-UMR200 (output 1)
- Metering must be enabled per device in the dSS Configurator
- Real-time updates via `deviceSensorValue` events; polled every 30s via cached `apartment/getDevices` (no bus traffic)
- `state_class: measurement` — fully compatible with the HA Energy Dashboard

### v3.0.0 (2026-05-12) — Major release

This is the 2.10.x development cycle rolled up into a single major release. Highlights versus 2.9.x:

**Energy Dashboard**
- Per-dSM (group) cumulative kWh sensor with `state_class=total_increasing`
- Apartment-wide kWh sensor as the sum of all dSMs
- Existing instantaneous Watt sensors retained

**dSS Configurator entities**
- *User Defined Actions* → HA buttons (raise the addon's `highlevelevent` with `id=<action>` parameter)
- *User Defined States* → binary_sensor / sensor entities, joined from all six addon categories (custom / combined / triggered / window / device-sensor / zone-sensor)
- *Klokken / Timers* → one button per timer to fire its configured actions on demand (zone-scene + device-scene sequenced with per-action delay)

**Per-component status**
- Every output-capable non-Joker device gets a diagnostic `binary_sensor` exposing its current `on` state from `apartment/getDevices` — no dS-bus traffic, single shared HTTP poll

**Hardening (from GPT-4o code review)**
- `asyncio.TimeoutError` now mapped to `DigitalStromApiError` in the request layer
- Background event-listener startup wrapped in a `try/except` so a crash is logged instead of silently lost
- Binary poll loop logs full traceback on unexpected exceptions

**Brand assets** — bundled in repo under `custom_components/digitalstrom_smart/brand/` so HACS default-repository validation passes (HA 2026.3+).

### v2.10.9 (2026-05-12)
- **Run-once timer button** — each Configurator timer now has a `button.run_<timer>` that fires its configured actions immediately, on demand. The button reads the timer's action list (zone-scene + device-scene) from the dSS property tree and replays it through the regular scene API
- **Removed**: timer enable/disable switch. Toggling klokken on/off stays in the dSS Configurator as Rene requested — only the manual fire-once stays in HA
- Per-action `delay` honoured when sequencing
- Attributes on the run-once button: `enabled_in_dss`, `last_executed`, `time_base`, `offset_seconds`, `recurrence_base`, `timer_id`

### v2.10.8 (2026-05-12)
- **Per-device output status** — every output-capable dS device (lights, shades, klimaat actuators) gets a diagnostic `binary_sensor.<device> status` showing whether the component is currently on. Sourced from `apartment/getDevices` web API only — no dS-bus polling, no extra HTTP-call (parsed from the existing 5-second device poll that already runs for binary inputs)
- Joker devices keep their existing `switch` entity — no duplicates
- Attributes: `dsuid`, `hw_info`, `output_mode`, `is_present`, `is_valid`. Entity becomes `unavailable` when the dSS reports `isPresent=false`

### v2.10.7 (2026-05-12)
- **One entity per timer** — the separate `sensor.<timer>` is gone; only the `switch.<timer>` remains. The switch state shows whether the timer is enabled, and the `last_executed` timestamp is now an attribute on the switch alongside `time_base`, `offset_seconds`, `recurrence_base` and `timer_id`
- All timers (enabled and disabled) appear as switches; toggling the switch updates the dSS via `property/setBoolean`
- **Migration note**: the old `sensor.<timer>` entities (from v2.10.4-v2.10.6) become orphaned in HA's entity registry. Either delete them manually under *Settings > Devices & Services > Entities*, or leave them — they'll be cleaned up automatically when the integration is reloaded once

### v2.10.6 (2026-05-12)
- **Full coverage of User Defined States** — v2.10.3 only imported `custom-states`. This release adds the five remaining categories: `combined-states`, `triggered-states`, `window-states`, `device-sensor-states`, `zone-sensor-states`. Examples: "Melder meeting", "Heater", "Roldeur open", "Warmtevraag", "Vorstbeveiliging 8-10gr.", "Oververhitting"
- Sensor-threshold based states (device/zone sensor) join their runtime value via `completeName` (e.g. `dev.<dsuid>.type9.<id>` or `zone.zoneN.groupX.type9.<id>`) instead of the numeric id
- New attributes on each binary_sensor: `category`, `active_value`, `inactive_value` (for sensor-threshold states)
- stateChange events now match on either the state id or its `completeName` lookup key

### v2.10.5 (2026-05-12)
- **Timer enable/disable switch** — each imported timer also gets a `switch` entity that writes to `/scripts/system-addon-timed-events/entries/<id>/conditions/enabled` via the dSS property tree. Toggle a klok on or off from Home Assistant without opening the Configurator
- `set_timer_enabled()` coordinator helper + `api.set_property_boolean()` for general boolean property writes

### v2.10.4 (2026-05-12)
- **Timers / Klokken import** — every Timed Event from the dSS Configurator (sunset/sunrise/dawn/daily timers) is imported as a `sensor` with `device_class=timestamp`, value = `lastExecuted`. Attributes: `enabled`, `time_base` (sunset/sunrise/daily/…), `offset_seconds`, `recurrence_base`, `timer_id`
- Source: `/scripts/system-addon-timed-events/entries/*`

### v2.10.3 (2026-05-12)
- **Configurator User Defined States** — states created in the dSS Configurator (*Activities > User Defined States*) are now imported as `binary_sensor` entities with their human-readable name ("Schoonmaak", "Vitrage was dicht", …). The previous v2.10.x release only imported `/usr/states/` which contains zone/device/system states but not the custom user definitions
- Runtime values come from `/usr/addon-states/system-addon-user-defined-states/<id>`, names from `/scripts/system-addon-user-defined-states/custom-states/<id>` — joined on state id
- State changes propagate live via the existing `stateChange` event subscription
- Each entity exposes `set_name` and `reset_name` (the labels the user configured) as attributes

### v2.10.2 (2026-05-12)
- **Brand assets** — icon and logo bundled at `custom_components/digitalstrom_smart/brand/` so the integration meets the HACS default-repository requirements (since HA 2026.3 custom integrations ship their own brand assets instead of the `home-assistant/brands` repo)

### v2.10.1 (2026-05-12)
- **User Defined Action trigger fix** — pressing a button now raises `highlevelevent` with `id=<UDA_id>` as parameter, the event pattern the dSS UDA addon actually subscribes to (the old `event/raise?name=<UDA_id>` only acknowledged the event but never executed the action)
- **Friendly names for device-bound states** — states named like `dev.<dsuid>.status.playbacktype` now show as `<Device Name> Playbacktype` instead of the raw dSUID

### v2.10.0 (2026-05-12)
- **Energy Dashboard support** — every dSM (group) now reports cumulative energy in kWh with `device_class=energy` and `state_class=total_increasing`, so circuits show up in the HA Energy Dashboard out of the box
- **Apartment-wide kWh sensor** — aggregated lifetime energy across all dSMs (`sensor.dss_energy_consumption`)
- **User Defined Actions** — actions configured in the dSS Configurator are imported as HA `button` entities; pressing the button raises the corresponding dSS event
- **User Defined States** — custom and apartment-wide dSS states from `/usr/states` are imported as `sensor` (multi-value) or `binary_sensor` (active/inactive) entities with live updates from `stateChange` events
- New `button` platform and additional translation strings (EN/NL/DE)

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

## Privacy & Telemetry

This integration sends a minimal anonymous ping to WoonIoT once at startup and every 24 hours. This helps us understand how many installations are active and which HA versions are in use.

**What is sent:**

| Field | Value | Personal? |
|-------|-------|-----------|
| `v` | Integration version | No |
| `ha` | Home Assistant version | No |
| `zones` | Number of zones (integer) | No |
| `devices` | Number of devices (integer) | No |
| `dss_id` | First 8 characters of dSS machine ID | Pseudonymous |
| `pro` | Pro license active (true/false) | No |

The receiving server is `ha-ds.internetist.nl` (operated by WoonIoT BV, hosted in the EU). Your IP address is technically received by the server as part of every HTTP request. No data is sold or shared with third parties. Full details: [wooniot.nl/privacy](https://www.wooniot.nl/privacy)

**Opt out:** Go to **Settings → Devices & Services → Digital Strom Smart → Configure** and disable the *Send anonymous telemetry* toggle. No data will be sent after saving.

> Note: Trial licenses require telemetry to be enabled. Paid Pro licenses work without telemetry.

## About

Developed by **[Woon IoT BV](https://wooniot.nl)** — professional Digital Strom installers and smart home specialists based in the Netherlands.

- Website: [wooniot.nl](https://wooniot.nl)
- Pro license: [wooniot.nl/pro](https://wooniot.nl/pro)
- Issues: [GitHub Issues](https://github.com/wooniot/ha-digitalstrom-smart/issues)
- License: [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/) — free for personal use, commercial use requires written permission from Woon IoT BV
