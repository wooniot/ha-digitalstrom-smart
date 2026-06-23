# Digital Strom Smart für Home Assistant

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/wooniot/ha-digitalstrom-smart)](https://github.com/wooniot/ha-digitalstrom-smart/releases)

Eine zonenbasierte, eventgesteuerte Home Assistant Integration für **Digital Strom** Hausautomationssysteme. Entwickelt von [Woon IoT BV](https://wooniot.nl) — Digital Strom Installationsspezialisten.

> [English](README.md) | **Deutsch** | [Nederlands](README.nl.md)

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
- **Leistungsüberwachung auf Wohnungsebene** — Gesamtverbrauch (W)
- **Alarm-Binärsensoren** — Feuer/Brand, Alarm 1-4, Panik und Türklingel als Binärsensoren unter dem Digital-Strom-Server-Gerät, mit Live-Updates aus dSS-Alarmereignissen
- **Systemszenen als Schalter** — Panik, Feuer/Brand, Alarm 1-4 und Türklingel wohnungsweit aus HA auslösen (über `apartment/callScene`); jeder Schalter liest den echten dSS-Zustand zurück und kehrt von selbst auf Aus zurück, wenn der dSS die Szene ignoriert
- **Umgebungszustände** — Tag/Nacht, Dämmerung, Tageslicht und Urlaub vom dSS als schreibgeschützte Binärsensoren
- **Eventgesteuert** — sofortige Status-Updates bei Betätigung eines Wandschalters
- **Szenen für alle Gruppen** — Licht-, Beschattungs- und Heizungsszenen

### Pro

Erweiterte Funktionen mit einem Pro-Lizenzschlüssel von [wooniot.nl/pro](https://wooniot.nl/pro):

- **Klimasteuerung** — Zieltemperatur, Voreinstellungen (Komfort, Sparen, Nacht, Urlaub), Heiz- und Kühlerkennung
- **Anwesenheitsmodus** — Anwesenheitsstatus der Wohnung lesen und setzen (Anwesend, Abwesend, Schlafen, …) als Select-Entität
- **Benutzerdefinierte Aktionen** — im dSS Konfigurator angelegte Aktionen erscheinen als Home-Assistant-**Buttons**
- **Benutzerdefinierte Zustände** — eigene und wohnungsweite dSS-Zustände erscheinen als **Sensoren / Binärsensoren** mit Live-Updates aus `stateChange`-Ereignissen
- **Energie pro Stromkreis (dSM)** — Leistung **und** kumulierte kWh pro dSM-Zähler, jeder als eigenes Gerät, bereit für das **HA Energie-Dashboard**
- **Wohnungs-kWh-Sensor** — aggregierte kumulierte Energie über alle dSMs (Energie-Dashboard)
- **Bewegung pro Zone** — Bewegungs-Binärsensoren pro Zone aus den dSS-Zuständen `zone.X.motion`
- **Störung & Wartung** — aggregierte Diagnose-Binärsensoren, die melden, wenn eine Komponente eine Störung oder Wartungsbedarf meldet
- **Außenwettersensoren** — Temperatur, Feuchtigkeit, Helligkeit, Windgeschwindigkeit, Windböen, Luftdruck (Wetterstation), zusätzlich stationslose Außentemperatur + Sonnenstand aus dem dSS-Wetterdienst
- **Regenerkennung** — Echtzeit-Regensensor über dSS-System-Protection-Ereignisse
- **Wetterschutz-Sensoren** — Wind-/Regenschutz-Szenenzustände als Binärsensoren
- **Geräteidentifikation** — Gerät blinken lassen zur Identifikation
- **Szenen speichern** — aktuelle Ausgabewerte als neue Szene speichern
- **Bereichsszenen** — voller Szenenbereich (6-9, 10-14, 20-24, 30-34, 40-44) plus alle benutzerdefinierten Szenen aus dem dSS

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
2. Oben rechts auf das Drei-Punkte-Menü (⋮) klicken
3. **Benutzerdefinierte Repositories** wählen
4. Diese URL hinzufügen: `https://github.com/wooniot/ha-digitalstrom-smart`
5. Kategorie: **Integration**
6. Auf **Hinzufügen** klicken
7. Jetzt nach "Digital Strom Smart" suchen und auf Installieren klicken
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

## Nach einem dSS-Firmware-Update (z. B. 1.19.13)

Ein Firmware-Update des dSS kann drei Dinge ändern, die die Anbindung betreffen. Die Integration fängt dies jetzt automatisch ab, aber gut zu wissen:

- **Die IP-Adresse kann sich ändern** (DHCP). Die Integration stellt die IP per Auto-Erkennung selbst wieder her, aber eine **feste IP oder DHCP-Reservierung** für das dSS vermeidet das vollständig. **Empfohlen.**
- **Das App-Token kann ungültig werden.** Home Assistant zeigt dann eine Meldung **„Erneute Authentifizierung erforderlich"**. Klicken Sie darauf, genehmigen Sie das neue Token in der dSS-Weboberfläche (**System > Zugriffsberechtigung**) und klicken Sie auf Senden. Ihre Einstellungen, Pro-Lizenz und Entitäten bleiben erhalten — ein erneutes Koppeln ist nicht nötig.
- **Die interne dSS-Kennung kann sich ändern.** Dadurch kann eine **Pro-Lizenz vorübergehend getrennt** werden. Dies wird auf unserer Seite (serverseitig) automatisch neu gebunden; funktioniert Pro nach einem Update nicht mehr, wenden Sie sich an info@wooniot.nl.

> **Tipp:** Eine feste IP für das dSS verhindert die Hälfte der Probleme. Prüfen Sie nach einem großen Firmware-Sprung, ob alle Entitäten wieder Werte anzeigen.

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

> **Hinweis:** Sensoren für Geräte-Leistung (W) und Geräte-Energie (Wh) wurden in v3.7.6 entfernt. Ihr Auslesen erforderte das Pollen des dSS-Sensorbusses, was den dSM-Messcontroller aushungerte und die dSM-Energiewerte verfälschte. Leistung und Energie werden jetzt nur noch auf dSM-(Stromkreis-)Ebene gemessen — siehe *Pro Stromkreis (dSM-Zähler)* unten.

Wohnungsebene (Kostenlos):
- `sensor.dss_power_consumption` — Gesamtleistung (Watt)

Alarm- & Systemzustände (Digital-Strom-Server-Gerät) — **Kostenlos**:
- `binary_sensor.dss_fire` — Feueralarm (Brand), Geräteklasse: smoke
- `binary_sensor.dss_alarm_1` … `alarm_4` — Alarmzustände 1-4
- `binary_sensor.dss_panic` / `dss_doorbell` — Panik / Türklingel
- `binary_sensor.dss_frost` / `hail` / `wind` / `rain` — Wetter-/Schutzzustände (schreibgeschützt)
- `binary_sensor.dss_daynight` / `twilight` / `daylight` / `holiday` — Umgebungszustände (schreibgeschützt)
- `switch.dss_fire`, `switch.dss_alarm_1` … `alarm_4`, `switch.dss_panic`, `switch.dss_doorbell` — Lösen die passende Wohnungsszene über `apartment/callScene` aus. Der Schalter spiegelt den echten dSS-Zustand und kehrt von selbst auf Aus zurück, wenn der dSS die Szene ignoriert

Pro Stromkreis (dSM-Zähler) — **Pro**:
- `sensor.<circuit_name>_power` — Leistung pro dSM-Zähler (jeder Zähler als eigenes Gerät)
- `sensor.<circuit_name>_energy` — Kumulierte Energie pro dSM (kWh, `total_increasing`)
- `sensor.dss_energy_consumption` — Wohnungsweite kWh, Summe aller dSMs (Energie-Dashboard)

> **Unterstützte dSM-Zähler:** dSM12, dSM20 und dSM25 werden gemessen (Leistung **und** Energie). Der End-of-Life-dSM11 wird ausgeschlossen, da er keine zuverlässige Messung liefert.

Benutzerdefinierte Aktionen & Zustände (Wohnung) — **Pro**:
- `button.<aktionsname>` — Ein Button pro im dSS Konfigurator definierter Aktion
- `sensor.<zustandsname>` / `binary_sensor.<zustandsname>` — Eine Entität pro eigenem/wohnungsweitem Zustand

Weitere Pro-Entitäten (Lizenz erforderlich):
- `climate.<zone>_climate` — Zonen-Klimasteuerung mit Zieltemperatur
- `select.<...>_presence` — Anwesenheitsmodus der Wohnung (Anwesend / Abwesend / Schlafen / …)
- `binary_sensor.<zone>_motion` — Bewegung pro Zone (dSS-Zustände `zone.X.motion`)
- `binary_sensor.dss_malfunction` / `dss_service` — Aggregierte Störung / Wartungsbedarf (Diagnose)
- `sensor.dss_outdoor_*` — Außenwetterstation-Sensoren
- `sensor.dss_ws_outdoor_temperature` / Sonnenstand — Stationslose Außendaten aus dem dSS-Wetterdienst
- `binary_sensor.dss_rain` — Regenerkennung

## Dienste

| Dienst | Beschreibung | Pro |
|--------|--------------|-----|
| `digitalstrom_smart.call_scene` | Szene aktivieren (zone_id, group, scene_number) | |
| `digitalstrom_smart.blink_device` | Gerät blinken lassen zur Identifikation (dsuid) | Ja |
| `digitalstrom_smart.save_scene` | Aktuelle Ausgabewerte als Szene speichern | Ja |

## Hinweise zur Klimasteuerung

### Passive Kühlung
Digital Strom verwendet **passive Kühlung** — der dSS steuert die Kühlleistung nicht aktiv. Wenn das System in den Kühlmodus wechselt:
- Die Klimaentität zeigt **Cooling** in Home Assistant
- Beim Anpassen der Zieltemperatur wird die Entität kurzzeitig als **Idle** angezeigt — das ist normal
- Das Zurückschalten auf Heizung dauert 1–2 Minuten (wird vom dSS gesteuert)
- Der im dSS konfigurierte minimale Sollwert gilt während des Kühlmodus

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

## Übersetzungen

Digital Strom Smart unterstützt mehrere Sprachen für alle Entitätsnamen, Konfigurationsbildschirme und Statuswerte:

| Sprache | Status |
|---------|--------|
| English | Vollständig |
| Nederlands (Niederländisch) | Vollständig |
| Deutsch | Vollständig |

Home Assistant verwendet automatisch die richtige Sprache basierend auf Ihrer Systemspracheinstellung. Möchten Sie eine Übersetzung hinzufügen? PRs willkommen — erstellen Sie einfach eine neue JSON-Datei in `custom_components/digitalstrom_smart/translations/`.

## Änderungsprotokoll

### v4.1.0 (23.06.2026) — Robust gegen Firmware-Updates

- **Automatische erneute Authentifizierung** — wird das dSS-App-Token ungültig (häufig nach einem dSS-Firmware-Update), zeigt Home Assistant nun eine Meldung *"Erneute Authentifizierung erforderlich"*, statt die Einrichtung stillschweigend fehlschlagen zu lassen. Das Genehmigen eines neuen Tokens behält Eintrag, Pro-Lizenz und alle Entitäten — kein Löschen und erneutes Koppeln nötig.
- **Verbindungsfehler werden erneut versucht** — ein vorübergehender Verbindungsfehler löst nun `ConfigEntryNotReady` aus (HA versucht es automatisch erneut), statt dauerhaft fehlzuschlagen.
- **Periodische Pro-Lizenzprüfung** — die Lizenz wird alle 6 Stunden neu validiert, sodass eine serverseitige Neubindung (nach einem Firmware-ID-Wechsel) ohne HA-Neustart erkannt wird; eine Free⇄Pro-Änderung lädt den Eintrag automatisch neu.
- **Reparatur-Hinweis "Pro-Lizenz inaktiv"** — ist ein Pro-Schlüssel konfiguriert, validiert aber nicht mehr, wird eine klare Meldung angezeigt (verschwindet, sobald wieder gültig), sodass verschwundene Pro-Funktionen nicht mehr stillschweigend sind.
- **README** — Abschnitt "Nach einem dSS-Firmware-Update (1.19.13)" mit Hinweisen hinzugefügt (feste IP empfohlen, Reauth, serverseitige Lizenz-Neubindung).

### v4.0.2 (19.06.2026) — dSM12-Messung unterstützt

- **dSM12 in die Stromkreis-Messung aufgenommen** — dSM12-Zähler liefern jetzt Leistung (W) und kumulierte Energie (Wh), genau wie dSM20/dSM25. Nur der End-of-Life-dSM11 wird übersprungen. Frühere Versionen schlossen dSM12 aus; dies wurde auf einer reinen dSM12-Installation verifiziert. Die zuvor auftretende Energie-Verfälschung kam von `getSensorValue2`-Bus-Starvation, die separat behoben ist (Geräte-Leistung ist event-only), sodass die dSM12-Messung sicher ist.

### v4.0.0 (12.06.2026) — Systemszenen, robuste Messung & Umgebungszustände

- **Systemalarmszenen als Schalter** — Feuer/Brand und Alarm 1-4 erhalten jetzt einen Schalter (neben dem schreibgeschützten Status-Binärsensor), der die Szene über `apartment/callScene` auslöst. Jeder Schalter liest den echten dSS-Zustand zurück und kehrt von selbst auf Aus zurück, wenn der dSS die Szene ignoriert.
- **Umgebungszustände (Kostenlos)** — Tag/Nacht, Dämmerung, Tageslicht und Urlaub als schreibgeschützte Binärsensoren.
- **Bewegung pro Zone + Störung/Wartung (Pro)** — Bewegungs-Binärsensoren pro Zone sowie aggregierte Störungs- und Wartungs-Diagnose.
- **Wetterdienst (Pro)** — stationslose Außentemperatur und Sonnenstand aus dem dSS-Wetterdienst.
- **Messung überarbeitet** — Sensoren für Geräte-Leistung (W) und -Energie (Wh) wurden entfernt: ihr Pollen hungerte den dSM-Messcontroller aus und verfälschte die dSM-Energiewerte. Leistung und Energie werden jetzt nur noch auf dSM-(Stromkreis-)Ebene gelesen; Geräte-Leistung ist eventgesteuert, wird nie gepollt.
- **Zuverlässigkeit** — Rekonfiguration bei IP-Wechsel + DHCP-Erkennung, schnellerer nicht-blockierender Start und eine gehärtete Ereignisschleife (ein fehlerhaftes Ereignis kann die Schleife nicht mehr stoppen).

### v2.9.0 (29.03.2026)
- **Vollständige i18n** — alle Entitätsnamen jetzt über das native Home Assistant Übersetzungssystem übersetzbar
- **Deutsche Übersetzung** — vollständige DE-Übersetzung für alle Entitäten, Konfigurationsflow und Optionen
- **Niederländische Übersetzung** — vollständige NL-Übersetzung für alle Entitäten
- Übersetzt: Sensoren, Lichter, Beschattung, Klima, Schalter, Anwesenheitsmodus (mit Statuswerten), Binärsensoren, Szenen (einschließlich Bereichsszenen)
- **Breaking Change**: Anwesenheitsmodus-Optionen von Anzeigenamen (`"Present"`, `"Absent"`) zu internen Schlüsseln (`"present"`, `"absent"`) geändert. Automatisierungen mit `select.select_option` entsprechend aktualisieren.

### v2.8.7 (24.03.2026)
- **Binärsensor Debug-Logging** — verbessertes Diagnose-Logging für Joker-Binärsensoren

### v2.8.6 (20.03.2026)
- **Binärsensor-Fix** — Kontaktsensoren (Türen, Fenster, UMR, EnOcean) melden jetzt den korrekten Offen/Geschlossen-Status
- **Schnelles Binär-Polling** — separater 5-Sekunden-Polling-Zyklus für Kontakt-/Tür-/Fenstersensoren (vorher 30s)
- **Korrekte API** — verwendet `apartment/getDevices` für Binäreingang-Status (zuverlässig über alle dSS-Firmware-Versionen)
- **Polaritäts-Fix** — Kontaktsensoren korrekt invertiert (dSS "aktiv"=geschlossen, HA an=offen). Bewegung/Anwesenheit unverändert.
- **Bereichsszenen** (Pro) — Unterstützung für Szenen 6-9, 10-14, 20-24, 30-34, 40-44
- **Dynamische Szenenerkennung** (Pro) — erstellt automatisch Entitäten für alle erreichbaren und benannten Szenen aus dem dSS

### v2.8.0 (17.03.2026)
- **Kühlmodus-Erkennung via Event** — verwendet `heating_system_mode` stateChange-Event (active=Heizung, inactive=Kühlung) als primäre Erkennungsmethode
- Wenn dSS auf Kühlung umschaltet, liefert die Heizungs-API nur `{ControlMode: 0}` ohne Kühlindikator — das eigentliche Signal ist das Apartment-Level-Event
- Kühlprüfung läuft vor der Aus-Erkennung in `hvac_mode` und `hvac_action`
- Passive Kühlung dokumentiert (siehe Hinweise zur Klimasteuerung)

### v2.4.0 (13.03.2026)
- **Energieüberwachung pro Stromkreis (dSM)** in die kostenlose Stufe verschoben — jeder dSM-Zähler als eigenes Gerät mit Leistungssensor
- **Sensor-Zuverlässigkeit** — dSS Zone-API für vorskalierte Werte, alle manuelle Bus-Kodierung entfernt
- Automatische dSM-Filterung (virtuelle Controller ausgeschlossen)
- Sensorwerte stimmen jetzt immer exakt mit dem dSS überein, unabhängig vom Gerätetyp

### v2.2.0 (11.03.2026)
- **Kostenlos/Pro-Stufen-Aufteilung** mit Lizenzschlüsselsystem ([wooniot.nl/pro](https://wooniot.nl/pro))
- **Individuelle Joker-Schalter** — Einzelgerätesteuerung mit Namen aus dem dS Konfigurator
- **Joker-Binärsensoren** — Kontakt-, Rauch-, Türsensoren mit automatischer Geräteklassenerkennung
- **Gerätesensoren** — Ulux CO2, Helligkeit, Temperatur, Feuchtigkeit als einzelne Entitäten
- **Klimasteuerung** (Pro) — Zieltemperatur, Voreinstellungen, Heiz- und Kühlerkennung
- **Außenwettersensoren** (Pro) — Temperatur, Feuchtigkeit, Helligkeit, Wind, Luftdruck, Regen
- **Szenenerkennung** mit benutzerdefinierten Namen aus dem dS Konfigurator
- Temperatur für Räume ohne Heizung (aus allen verfügbaren Quellen)

### v1.0.0 (10.03.2026)
- Erstveröffentlichung: zonenbasierte Beleuchtung, Beschattung, Szenen, Temperatursensoren, Energieüberwachung
- Eventgesteuerte Architektur mit Echtzeit-Status-Updates
- Lokale und Cloud-Verbindung

## Über uns

Entwickelt von **[Woon IoT BV](https://wooniot.nl)** — professionelle Digital Strom Installateure und Smart-Home-Spezialisten aus den Niederlanden.

- Website: [wooniot.nl](https://wooniot.nl)
- Pro-Lizenz: [wooniot.nl/pro](https://wooniot.nl/pro)
- Probleme melden: [GitHub Issues](https://github.com/wooniot/ha-digitalstrom-smart/issues)
- Lizenz: MIT
