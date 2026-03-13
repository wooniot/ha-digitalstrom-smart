# Digital Strom Smart für Home Assistant

[![HACS Badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/wooniot/ha-digitalstrom-smart)](https://github.com/wooniot/ha-digitalstrom-smart/releases)

Eine zonenbasierte, eventgesteuerte Home Assistant Integration für **Digital Strom** Hausautomationssysteme. Entwickelt von [Woon IoT BV](https://wooniot.nl) — Digital Strom Installationsspezialisten.

> **[English version](README.md)** | Deutsch

## Voraussetzungen

- **Digital Strom Server**: dSS20 oder neuer (Firmware 1.19.x+)
- **Home Assistant**: 2024.1.0 oder neuer
- **Verbindung**: Lokaler Netzwerkzugang zum dSS (HTTPS, Standardport 8080)

> Diese Integration verbindet sich direkt über das lokale Netzwerk mit Ihrem dSS. Keine Cloud-Verbindung oder digitalstrom.net-Konto erforderlich.

## Warum diese Integration?

Im Gegensatz zu herkömmlichen Integrationen, die jedes Gerät einzeln abfragen, nutzt Digital Strom Smart die **szenenbasierte Architektur**, für die Digital Strom entwickelt wurde:

| | Herkömmlicher Ansatz | Digital Strom Smart |
|--|---------------------|-------------------|
| **Steuerung** | Einzelne Gerätebefehle | Zonen-Szenen (ein Befehl, alle Geräte reagieren) |
| **Status-Updates** | Polling alle 10-30s pro Gerät | Echtzeit Event-Subscription |
| **Bus-Last** | ~50+ Anfragen/Min (10 Zonen) | ~0,4 Anfragen/Min + 1 Event-Verbindung |
| **Risiko** | Kann apartments.xml beschädigen | Sicher — verwendet nur Standard-API-Aufrufe |

## Funktionen

### Kostenlos

- **Zonenbasierte Beleuchtung** mit Helligkeitssteuerung (Dimmen via `setValue`)
- **Zonenbasierte Beschattung** (Jalousien/Rollläden) mit Positionssteuerung und Richtungsumkehr
- **Individuelle Joker-Schalter** — jeder Joker-Aktor erhält eine eigene Switch-Entität mit dem Gerätenamen aus dem dS Konfigurator
- **Joker-Binärsensoren** — Kontaktsensoren, Rauchmelder, Türkontakte werden automatisch als Binärsensoren mit der richtigen Geräteklasse erkannt
- **Szenenaktivierung** mit importierten dS-Szenennamen (die empfohlene Methode zur Steuerung von Digital Strom)
- **Temperatursensoren** pro Zone (auch Räume ohne Heizung, aus allen verfügbaren Quellen: Zonensensoren, Gerätesensoren)
- **Gerätesensoren** — Ulux und ähnliche Geräte stellen CO2, Helligkeit, Temperatur und Feuchtigkeit als einzelne Sensor-Entitäten bereit
- **Energieüberwachung** (Gesamtverbrauch auf Wohnungsebene)
- **Eventgesteuert** — sofortige Status-Updates bei Betätigung eines Wandschalters
- **Szenen für alle Gruppen** — Licht-, Beschattungs- und Heizungsszenen

### Pro

Erweiterte Funktionen mit einem Pro-Lizenzschlüssel von [wooniot.nl/pro](https://wooniot.nl/pro):

- **Klimasteuerung** — Zieltemperatur, Voreinstellungen (Komfort, Sparen, Nacht, Urlaub), Heiz- und Kühlerkennung
- **Außenwettersensoren** — Temperatur, Feuchtigkeit, Helligkeit, Wind, Luftdruck, Regenerkennung
- **Energieüberwachung pro Stromkreis** — Verbrauch pro dSM-Zähler
- **Geräteidentifikation** — Gerät blinken lassen zur Identifikation
- **Szenen speichern** — aktuelle Ausgabewerte als neue Szene speichern

#### Pro-Lizenz

Geben Sie Ihren Pro-Lizenzschlüssel in den Integrationsoptionen ein (**Einstellungen > Geräte & Dienste > Digital Strom Smart > Konfigurieren**). Lizenztypen:

| Typ | Laufzeit | Preis |
|-----|----------|-------|
| Testversion | 30 Tage | Kostenlos (Anfrage über [wooniot.nl/pro](https://wooniot.nl/pro)) |
| Jährlich | 365 Tage | €29/Jahr |
| Lebenslang | Permanent | €89 einmalig |

## Installation

### HACS (empfohlen)

1. HACS in Home Assistant öffnen
2. Nach "Digital Strom Smart" suchen
3. Auf Installieren klicken
4. Home Assistant neu starten

### Manuell

1. Neueste Version von [GitHub](https://github.com/wooniot/ha-digitalstrom-smart/releases) herunterladen
2. `custom_components/digitalstrom_smart/` in Ihr HA-Konfigurationsverzeichnis kopieren
3. Home Assistant neu starten

## Konfiguration

1. Gehen Sie zu **Einstellungen > Geräte & Dienste > Integration hinzufügen**
2. Suchen Sie nach **Digital Strom**
3. Geben Sie die **IP-Adresse** und den **Port** (Standard 8080) Ihres dSS ein
4. Verbindung in der dSS-Administrationsoberfläche genehmigen:
   - Öffnen Sie die dSS-Weboberfläche im Browser
   - Gehen Sie zu **System > Zugriffsberechtigung**
   - Finden Sie **WoonIoT HA Connect** und aktivieren Sie das Kontrollkästchen
5. Auf Absenden klicken — die Integration erkennt automatisch alle Zonen und Geräte

### Optionen

Nach der Einrichtung können Sie in den Integrationsoptionen:
- **Zonen auswählen**, die in Home Assistant eingebunden werden sollen
- **Beschattungsrichtung umkehren**, falls Jalousien/Rollläden in die falsche Richtung fahren
- **Pro-Lizenzschlüssel eingeben**, um erweiterte Funktionen freizuschalten

## Erstellte Entitäten

Für jede Zone mit Geräten:
- `light.<zone>_light` — Zonen-Lichtsteuerung (Ein/Aus/Helligkeit)
- `cover.<zone>_cover` — Zonen-Beschattung (Öffnen/Schließen/Position)
- `scene.<zone>_<szenenname>` — dS-Voreinstellungen aktivieren (mit benutzerdefinierten Namen aus dS)
- `sensor.<zone>_temperature` — Zonentemperatur (aus allen verfügbaren Quellen)

Individuelle Joker-Geräte:
- `switch.<zone>_<gerätename>` — Einzelgeräte-Steuerung (Aktoren mit outputMode > 0)
- `binary_sensor.<zone>_<gerätename>` — Kontakt-/Rauch-/Türsensoren (Geräte mit outputMode == 0)

Gerätesensoren (Ulux usw.):
- `sensor.<zone>_<gerät>_temperature` — Gerätetemperatur
- `sensor.<zone>_<gerät>_humidity` — Gerätefeuchtigkeit
- `sensor.<zone>_<gerät>_co2` — Geräte-CO2-Wert
- `sensor.<zone>_<gerät>_brightness` — Gerätehelligkeit

Wohnungsebene:
- `sensor.dss_power_consumption` — Gesamtleistung (Watt)

Pro-Entitäten (Lizenz erforderlich):
- `climate.<zone>_climate` — Zonen-Klimasteuerung mit Zieltemperatur
- `sensor.dss_outdoor_*` — Außenwettersensoren
- `sensor.dss_circuit_*_power` — Verbrauch pro Stromkreis
- `binary_sensor.dss_rain` — Regenerkennung

## Dienste

| Dienst | Beschreibung | Pro |
|--------|--------------|-----|
| `digitalstrom_smart.call_scene` | Szene aktivieren (zone_id, group, scene_number) | |
| `digitalstrom_smart.blink_device` | Gerät blinken lassen zur Identifikation (dsuid) | Ja |
| `digitalstrom_smart.save_scene` | Aktuelle Ausgabewerte als Szene speichern | Ja |

## Architektur

```
Home Assistant
  │
  └── Digital Strom Smart
        │
        ├── Event Listener (Long-Poll)
        │     ├── callScene / undoScene → Licht, Beschattung, Schalter, Szenen
        │     ├── zoneSensorValue → Temperatursensoren
        │     ├── deviceSensorValue → Gerätesensoren (Ulux CO2/Lux/Temp)
        │     └── stateChange → Binärsensoren (Kontakte, Rauch, Tür)
        │
        ├── Polling (alle 5 Min.)
        │     ├── getConsumption → Energiesensor
        │     ├── getTemperatureControlValues → Zonentemperaturen
        │     └── PRO: getSensorValues, getCircuits, Klimastatus
        │
        └── Befehle
              ├── callScene / setValue → Zonen-Licht, Beschattung, Szenen
              └── device/turnOn / turnOff → Individuelle Joker-Schalter
```

## Unterstützte Hardware

- **dSS20** (Minimum) oder neuerer Digital Strom Server
- Alle Digital Strom Gerätetypen: GE (Licht), GR (Beschattung), SW (Joker/Schwarz), BL (Jalousie)
- Joker-Aktoren (Relais, Schalter) — einzeln steuerbar
- Joker-Sensoren (Kontakte, Rauchmelder, Türsensoren) — automatische Geräteklassenerkennung
- Ulux und ähnliche Multisensor-Geräte (CO2, Helligkeit, Temperatur, Feuchtigkeit)
- dSM-Zähler (Energieüberwachung)
- Außenwetterstationen (Temperatur, Feuchtigkeit, Helligkeit, Wind, Luftdruck, Regen)
- Klimazonen (Heizung und Kühlung)

## Änderungsprotokoll

### v2.3.3 (13.03.2026)
- Zone/getSensorValues API für initiale Sensorwerte (vom dSS vorskaliert)
- Alle manuelle Bus-Kodierung entfernt (raw/40, raw/100) — der dSS skaliert selbst
- getSensorValue API-Aufrufe komplett entfernt — kein Sensor-Polling pro Gerät
- Code-Bereinigung: Helper extrahiert, toter Code entfernt, Import-Platzierung korrigiert
- Der dSS übernimmt alle Bus-Encoding-Konvertierungen — keine manuelle Skalierung nötig
- Entfernt fragile gerätespezifische Skalierungslogik (raw/40, raw/100 usw.)
- Sensorwerte stimmen jetzt immer mit dem überein, was der dSS meldet

### v2.3.0 (12.03.2026)
- dS-Bus Sensor-Skalierung korrigiert: offizielle dS-Bus 12-Bit-Kodierung pro Sensortyp
- Temperatur: `raw / 40 - 43.2`, Luftfeuchtigkeit: `raw / 40` (nicht raw/100)
- Gegen dSS Zone-API-Werte verifiziert — stimmt jetzt exakt überein
- Behebt falsche Luftfeuchtigkeit (zeigte ~22% statt ~56%) und Temperaturabweichungen bei dS-Bus-Geräten

### v2.2.9 (12.03.2026)
- Sensor-Skalierung behoben: dSUID-Präfix zur zuverlässigen Erkennung von dS-Bus-Geräten (immer Roh /100) vs. EnOcean-Geräten (bereits Float)
- Behebt falsche Helligkeits- und CO2-Werte (z.B. 2149 lx statt 21,49 lx)
- Entfernt unzuverlässige bereichsbasierte Heuristik zugunsten deterministischer dSUID-Präfix-Prüfung

### v2.2.8 (12.03.2026)
- Geräte-Sensor-Skalierung behoben: intelligente Erkennung von Roh-Integer vs. Float-Werten aus der dSS-API
- EnOcean-Sensoren (Thermokon) liefern korrekte Floats, dS-Bus-Sensoren (FTW04, TNY210) liefern Roh-Integer — beide werden jetzt korrekt verarbeitet
- FTW04 Temperatur-/Feuchtigkeitssensoren zeigen jetzt korrekte Werte
- Ulux/TNY210 CO2-, Helligkeits-, Temperatur- und Feuchtigkeitssensoren unterstützt
- Verbesserte Startup-Protokollierung für Geräte-Sensor-Erkennung

### v2.2.5 (12.03.2026)
- Joker-Aktoren (outputMode > 0) erstellen jetzt **Switch**-Entitäten
- Joker-Sensoren (outputMode == 0) erstellen jetzt **Binary Sensor**-Entitäten mit automatischer Geräteklassenerkennung (Tür, Fenster, Rauch, Bewegung usw.)
- binary_sensor-Plattform in die kostenlose Stufe verschoben

### v2.2.4 (12.03.2026)
- Sensorwerte wurden 100x zu hoch angezeigt — behoben (`sensorValueFloat` statt `sensorValue` aus dSS-Events)

### v2.2.3 (12.03.2026)
- Individuelle Joker-Geräteschalter mit Namen aus dem dS Konfigurator
- Gerätesteuerung über `/json/device/turnOn` und `/json/device/turnOff`

### v2.2.0 (11.03.2026)
- Ulux-Gerätesensoren (CO2, Helligkeit, Temperatur, Feuchtigkeit)
- Kühlerkennung für Klimasteuerung (HVACMode.COOL)
- Temperatur für Räume ohne Heizung (aus allen verfügbaren Quellen)
- Joker (Gruppe 8) Unterstützung
- Regensensor von Außenwetterstation
- Pause/Fortsetzen entfernt (nicht mehr erforderlich)
- Verbesserungen der Telemetrie-Zuverlässigkeit

### v2.0.0 (10.03.2026)
- Kostenlos/Pro-Stufen-Aufteilung mit Lizenzschlüsselsystem
- Klimasteuerung (Pro)
- Außenwettersensoren (Pro)
- Energieüberwachung pro Stromkreis (Pro)
- Szenenerkennung mit benutzerdefinierten Namen

### v1.0.0
- Erstveröffentlichung: Beleuchtung, Beschattung, Szenen, Sensoren, Energie

## Über uns

Entwickelt von **[Woon IoT BV](https://wooniot.nl)** — professionelle Digital Strom Installateure und Smart-Home-Spezialisten aus den Niederlanden.

- Website: [wooniot.nl](https://wooniot.nl)
- Pro-Lizenz: [wooniot.nl/pro](https://wooniot.nl/pro)
- Probleme melden: [GitHub Issues](https://github.com/wooniot/ha-digitalstrom-smart/issues)
- Lizenz: MIT
