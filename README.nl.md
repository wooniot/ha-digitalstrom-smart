# Digital Strom Smart voor Home Assistant

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/wooniot/ha-digitalstrom-smart)](https://github.com/wooniot/ha-digitalstrom-smart/releases)

Een zone-gebaseerde, event-gestuurde Home Assistant-integratie voor **Digital Strom** domotica. Gebouwd door [Woon IoT BV](https://wooniot.nl) — Digital Strom installatiespecialisten.

> [English](README.md) | [Deutsch](README.de.md) | **Nederlands**

## Vereisten

- **Digital Strom Server**: dSS20 of nieuwer (firmware 1.19.x+)
- **Home Assistant**: 2024.1.0 of nieuwer
- **Verbinding**: lokale netwerktoegang tot je dSS (HTTPS, standaardpoort 8080)

> Deze integratie verbindt rechtstreeks met je dSS via je lokale netwerk. Geen cloudverbinding of digitalstrom.net-account nodig.

## Waarom deze integratie?

Anders dan traditionele integraties die per apparaat pollen, gebruikt Digital Strom Smart de **scene-gebaseerde architectuur** waarvoor Digital Strom is ontworpen:

| | Traditionele aanpak | Digital Strom Smart |
|--|---------------------|-------------------|
| **Bedieningswijze** | Individuele apparaatcommando's | Zonescenes (één commando, alle apparaten reageren) |
| **Status-updates** | Polling elke 10-30s per apparaat | Realtime event-abonnement |
| **Busbelasting** | ~50+ verzoeken/min (10 zones) | ~0,4 verzoeken/min + 1 event-verbinding |
| **Risico** | Kan apartments.xml beschadigen | Veilig — gebruikt alleen standaard-API-calls |

## Functies

### Gratis

- **Zone-gebaseerde verlichting** met dimmen (via `setValue`)
- **Zone-gebaseerde rolluiken/screens** met positiebesturing en richtingsomkering
- **Individuele Joker-schakelaars** — elke Joker-actor krijgt een eigen schakelaar-entiteit met de apparaatnaam uit de dS Configurator
- **Joker-binarysensoren** — contactsensoren, rookmelders en deurcontacten worden automatisch herkend als binarysensoren met de juiste device class
- **Scene-activering** met geïmporteerde dS-scenenamen (de aanbevolen manier om Digital Strom te bedienen)
- **Temperatuursensoren** per zone (ook ruimtes zonder verwarming, uit elke beschikbare bron: zonesensoren, apparaatsensoren)
- **Apparaatsensoren** — Ulux en vergelijkbare apparaten stellen CO2, helderheid, temperatuur en luchtvochtigheid beschikbaar als losse sensor-entiteiten
- **Vermogensmeting op woningniveau** — totaalverbruik (W)
- **Alarm-binarysensoren** — Brand, Alarm 1-4, Paniek en Deurbel verschijnen als binarysensoren onder het Digital Strom Server-apparaat, met live updates uit dSS-alarmgebeurtenissen
- **Systeemscene-schakelaars** — Paniek, Brand, Alarm 1-4 en Deurbel woningbreed activeren vanuit HA als schakelaars (via `apartment/callScene`); elke schakelaar leest de echte dSS-status terug en springt vanzelf terug naar uit als de dSS de scene negeert
- **Omgevingsstatussen** — Dag/Nacht, Schemering, Daglicht en Vakantie vanuit de dSS als alleen-lezen binarysensoren
- **Event-gestuurd** — directe status-updates wanneer iemand een wandschakelaar gebruikt
- **Scenes voor alle groepen** — Licht-, Beschaduwings- en Verwarmingsscenes

### Pro

Ontgrendel geavanceerde functies met een Pro-licentiesleutel van [wooniot.nl/pro](https://wooniot.nl/pro):

- **Klimaatregeling** — streeftemperatuur, voorinstellingen (Comfort, Spaarstand, Nacht, Vakantie), detectie van verwarmen + koelen
- **Aanwezigheidsmodus** — de aanwezigheidsstatus van de woning lezen en instellen (Aanwezig, Afwezig, Slapen, …) als select-entiteit
- **Gebruikersgedefinieerde acties** — acties uit de dSS Configurator verschijnen als Home Assistant-**knoppen**
- **Gebruikersgedefinieerde statussen** — eigen en woningbrede dSS-statussen verschijnen als **sensoren / binarysensoren** met live updates uit `stateChange`-gebeurtenissen
- **Energie per stroomkring (dSM)** — vermogen **én** levensduur-kWh per dSM-meter, elk als eigen apparaat, klaar voor het **HA Energie-dashboard**
- **Woning-kWh-sensor** — geaggregeerde cumulatieve energie over alle dSM's (Energie-dashboard)
- **Beweging per zone** — bewegings-binarysensoren per zone uit de dSS-statussen `zone.X.motion`
- **Storing & service** — geaggregeerde diagnose-binarysensoren die melden wanneer een component een storing of servicebehoefte meldt
- **Buitenweersensoren** — temperatuur, luchtvochtigheid, helderheid, windsnelheid, windvlagen, luchtdruk (weerstation), plus een stationsloze buitentemperatuur + zonpositie uit de dSS-weerdienst
- **Regendetectie** — realtime regensensor via dSS-systeembeveiligingsgebeurtenissen
- **Weerbeschermingssensoren** — wind-/regenbeschermingsscene-statussen als binarysensoren
- **Apparaatidentificatie** — een apparaat laten knipperen ter identificatie
- **Scenes opslaan** — huidige uitgangswaarden opslaan als nieuwe scene
- **Areascenes** — volledige scenereeks (6-9, 10-14, 20-24, 30-34, 40-44) plus alle gebruikersgedefinieerde scenes uit de dSS

#### Pro-licentie

Voer je Pro-licentiesleutel in bij de integratie-opties (**Instellingen > Apparaten & Diensten > Digital Strom Smart > Configureren**). Licentietypes:

| Type | Duur | Prijs |
|------|------|-------|
| Proef | 30 dagen | Gratis (aanvragen via [wooniot.nl/pro](https://wooniot.nl/pro)) |
| Jaarlijks | 365 dagen | €29/jaar |
| Levenslang | Permanent | €89 eenmalig |

## Installatie

### HACS (aanbevolen)

1. Open HACS in Home Assistant
2. Klik op het menu met drie puntjes (⋮) rechtsboven
3. Kies **Custom repositories**
4. Voeg deze URL toe: `https://github.com/wooniot/ha-digitalstrom-smart`
5. Categorie: **Integration**
6. Klik **Add**
7. Zoek nu naar "Digital Strom Smart" en klik op Installeren
8. Herstart Home Assistant

### Handmatig

1. Download de nieuwste release van [GitHub](https://github.com/wooniot/ha-digitalstrom-smart/releases)
2. Kopieer `custom_components/digitalstrom_smart/` naar je HA-configuratiemap
3. Herstart Home Assistant

## Configuratie

1. Ga naar **Instellingen > Apparaten & Diensten > Integratie toevoegen**
2. Zoek naar **Digital Strom**
3. Voer het **IP-adres** en de **poort** (standaard 8080) van je dSS in
4. Keur de verbinding goed in je dSS-beheerinterface:
   - Open de dSS-webinterface in je browser
   - Ga naar **Systeem > Toegangsautorisatie**
   - Zoek **WoonIoT HA Connect** en vink het vakje aan om goed te keuren
5. Klik op Verzenden — de integratie ontdekt automatisch alle zones en apparaten

### Opties

Ga na de installatie naar de integratie-opties om:
- **Zones te selecteren** die je in Home Assistant wilt opnemen
- **De rolluikrichting om te keren** als schermen de verkeerde kant op bewegen
- **Je Pro-licentiesleutel in te voeren** om geavanceerde functies te ontgrendelen

## Na een dSS firmware-update (bijv. 1.19.13)

Een firmware-update van de dSS kan drie dingen veranderen die de koppeling raken. De integratie vangt dit nu automatisch op, maar het is goed om te weten:

- **Het IP-adres kan wijzigen** (DHCP). De integratie herstelt het IP zelf via auto-detectie, maar een **vast IP of DHCP-reservering** voor de dSS voorkomt dit volledig. **Aanbevolen.**
- **Het app-token kan ongeldig worden.** Home Assistant toont dan een melding **"Herauthenticatie vereist"**. Klik erop, keur het nieuwe token goed in de dSS-webinterface (**Systeem > Toegangsautorisatie**) en klik op Verzenden. Je instellingen, Pro-licentie en entiteiten blijven behouden — opnieuw koppelen is niet nodig.
- **De interne dSS-identifier kan veranderen.** Hierdoor kan een **Pro-licentie tijdelijk losraken**. Dit wordt aan onze kant (server-side) automatisch opnieuw gebonden; werkt Pro na een update niet meer, neem dan contact op via info@wooniot.nl.

> **Tip:** een vast IP-adres voor de dSS voorkomt de helft van de problemen. Controleer na een grote firmware-sprong of alle entiteiten weer waarden tonen.

## Aangemaakte entiteiten

Per zone met apparaten:
- `light.<zone>_light` — Zonelicht (aan/uit/helderheid)
- `cover.<zone>_cover` — Zonerolluik (open/dicht/positie)
- `scene.<zone>_<scenenaam>` — dS-voorinstellingen activeren (met gebruikersnamen uit dS)
- `sensor.<zone>_temperature` — Zonetemperatuur (uit elke beschikbare bron)

Individuele Joker-apparaten:
- `switch.<zone>_<apparaatnaam>` — Bediening per apparaat (actoren met outputMode > 0)
- `binary_sensor.<zone>_<apparaatnaam>` — Contact-/rook-/deursensoren (apparaten met outputMode == 0)

Apparaatsensoren (Ulux enz.):
- `sensor.<zone>_<apparaat>_temperature` — Apparaattemperatuur
- `sensor.<zone>_<apparaat>_humidity` — Apparaatluchtvochtigheid
- `sensor.<zone>_<apparaat>_co2` — CO2-waarde apparaat
- `sensor.<zone>_<apparaat>_brightness` — Helderheid apparaat

> **Let op:** sensoren voor vermogen (W) en energie (Wh) per apparaat zijn verwijderd in v3.7.6. Het uitlezen vereiste polling van de dSS-sensorbus, wat de dSM-meetcontroller uithongerde en de dSM-energiewaarden beschadigde. Vermogen en energie worden nu uitsluitend op dSM-(stroomkring-)niveau gemeten — zie *Per stroomkring (dSM-meters)* hieronder.

Woningniveau (Gratis):
- `sensor.dss_power_consumption` — Totaalvermogen (Watt)
- `sensor.dss_license_status` — Licentiestatus: Pro/Gratis met validatiedetails (diagnostisch)

Alarm- & systeemstatussen (Digital Strom Server-apparaat) — **Gratis**:
- `binary_sensor.dss_fire` — Brandalarm, device class: smoke
- `binary_sensor.dss_alarm_1` … `alarm_4` — Alarmstatussen 1-4
- `binary_sensor.dss_panic` — Paniekalarm
- `binary_sensor.dss_doorbell` — Deurbel actief
- `binary_sensor.dss_frost` / `hail` / `wind` / `rain` — Weer-/beschermingsstatussen (alleen-lezen)
- `binary_sensor.dss_daynight` / `twilight` / `daylight` / `holiday` — Omgevingsstatussen (alleen-lezen)
- `switch.dss_fire`, `switch.dss_alarm_1` … `alarm_4`, `switch.dss_panic`, `switch.dss_doorbell` — Activeren de bijbehorende woningscene via `apartment/callScene`. De schakelaar spiegelt de echte dSS-status en springt vanzelf terug naar uit als de dSS de scene negeert

Per stroomkring (dSM-meters) — **Pro**:
- `sensor.<circuit_name>_power` — Momentaan vermogen per dSM-meter (W)
- `sensor.<circuit_name>_energy` — Cumulatieve energie per dSM (kWh, `total_increasing`)
- `sensor.dss_energy_consumption` — Woningbrede kWh, som van alle dSM's (Energie-dashboard)

> **Ondersteunde dSM-meters:** dSM12, dSM20 en dSM25 worden gemeten (vermogen **én** energie). De end-of-life dSM11 wordt uitgesloten, omdat die geen betrouwbare meting levert.

Gebruikersgedefinieerde acties & statussen (woning) — **Pro**:
- `button.<actienaam>` — Eén knop per actie uit de dSS Configurator
- `sensor.<statusnaam>` / `binary_sensor.<statusnaam>` — Eén entiteit per eigen/woningstatus, met live updates uit dSS-gebeurtenissen

Overige Pro-entiteiten (licentie vereist):
- `climate.<zone>_climate` — Zoneklimaatregeling met streeftemperatuur
- `select.<...>_presence` — Aanwezigheidsmodus woning (Aanwezig / Afwezig / Slapen / …)
- `binary_sensor.<zone>_motion` — Beweging per zone (dSS-statussen `zone.X.motion`)
- `binary_sensor.dss_malfunction` / `dss_service` — Geaggregeerde storing / servicebehoefte (diagnostisch)
- `sensor.dss_outdoor_*` — Buitenweerstation-sensoren
- `sensor.dss_ws_outdoor_temperature` / zonpositie — Stationsloze buitendata uit de dSS-weerdienst
- `binary_sensor.dss_rain` — Regendetectie
- `binary_sensor.dss_*_protection` — Wind-/regenbeschermingsscene-statussen

## Diensten

| Dienst | Beschrijving | Pro |
|--------|--------------|-----|
| `digitalstrom_smart.call_scene` | Een scene activeren (zone_id, group, scene_number) | |
| `digitalstrom_smart.blink_device` | Een apparaat laten knipperen ter identificatie (dsuid) | Ja |
| `digitalstrom_smart.save_scene` | Huidige uitgangswaarden opslaan als scene | Ja |

## Klimaatnotities

### Passief koelen
Digital Strom gebruikt **passief koelen** — de dSS regelt het koelvermogen niet actief. Wanneer het systeem naar koelmodus schakelt:
- De klimaat-entiteit toont **Koelen** in Home Assistant
- Het aanpassen van de streeftemperatuur toont de entiteit kort als **Inactief** — dit is normaal
- Het terugschakelen naar verwarmen duurt 1-2 minuten (door de dSS geregeld)
- De minimale setpoint die in de dSS is ingesteld geldt tijdens koelmodus

## Architectuur

```
Home Assistant
  │
  └── Digital Strom Smart
        │
        ├── Event Listener (long-poll)
        │     ├── callScene / undoScene → Licht, Rolluik, Schakelaar, Scene-status
        │     ├── zoneSensorValue → Temperatuursensoren
        │     ├── deviceSensorValue → Apparaatsensoren (Ulux CO2/Lux/Temp)
        │     ├── stateChange → Binarysensoren (contacten, rook, deur)
        │     └── stateChange → Regendetectie (woningniveau)
        │
        ├── Binaire-invoer-polling (elke 5s)
        │     └── apartment/getDevices → Contact-/deur-/raamstatus
        │
        ├── Polling (elke 30s)
        │     ├── getConsumption → Energiesensor
        │     ├── getTemperatureControlValues → Zonetemperaturen
        │     └── PRO: getSensorValues, getCircuits, klimaatstatus
        │
        └── Commando's
              ├── callScene / setValue → Zonelicht, rolluiken, scenes
              └── device/turnOn / turnOff → Individuele Joker-schakelaars
```

## Ondersteunde hardware

- **dSS20** (minimum) of nieuwere Digital Strom Server
- Alle Digital Strom-apparaattypes: GE (licht), GR (beschaduwing), SW (joker/zwart), BL (rolluiken)
- Joker-actoren (relais, schakelaars) — individueel bedienbaar
- Joker-sensoren (contacten, rookmelders, deursensoren) — automatisch herkende device class
- Ulux en vergelijkbare multisensorapparaten (CO2, helderheid, temperatuur, luchtvochtigheid)
- dSM-meters (energiemonitoring)
- Buitenweerstations (temperatuur, luchtvochtigheid, helderheid, windsnelheid/-vlaag, druk)
- Regendetectie via dSS-systeembeveiligingsstatus
- Klimaatregelzones (verwarmen en koelen)

## Vertalingen

Digital Strom Smart ondersteunt meerdere talen voor alle entiteitsnamen, configuratieschermen en statuswaarden:

| Taal | Status |
|------|--------|
| English | Volledig |
| Nederlands | Volledig |
| Deutsch | Volledig |

Home Assistant gebruikt automatisch de juiste taal op basis van je systeemtaal. Een vertaling toevoegen? PR's zijn welkom — maak een nieuw JSON-bestand aan in `custom_components/digitalstrom_smart/translations/`.

## Wijzigingslog

### v4.1.4 (25-06-2026) — Regelwaarde-sensor (koel-/verwarmvraag uit de DS)

- **Nieuwe sensor "Regelwaarde" per klimaatzone**: toont de aansturing van de DS-temperatuurregeling als waarde mét teken — **negatief = koelvraag, positief = verwarmvraag** (grootte = intensiteit). Werkt ook in koelmodus, waar een setpoint ontbreekt. De waarde wordt nu ook uit de per-zone temperatuurregeling-status gelezen (niet alleen de apartement-uitlezing), en de sensor wordt altijd aangemaakt voor zones met temperatuurregeling.

### v4.1.3 (25-06-2026) — Joker-schakelaar: juiste status na opstarten

- **Joker-actoren als schakelaar**: de status direct na het opstarten van de integratie is nu correct. Voorheen kon een actor vlak na de start ten onrechte als "aan" verschijnen omdat de beginstatus uit een onbetrouwbaar structuurveld kwam; deze wordt nu uit de werkelijke uitgangsstatus afgeleid (dezelfde bron als de status-poll). Aanvulling op v4.1.2.

### v4.1.2 (25-06-2026) — Joker-schakelaars volgen externe wijzigingen

- **Joker-actoren als schakelaar (SW-ZWS200, SW-SSL200 e.d.)**: een aan/uit-wijziging die buiten Home Assistant om wordt gedaan (via de Digital Strom-app of een fysieke schakelaar) wordt nu correct in HA weergegeven. Voorheen werd de status alleen bijgewerkt bij bediening via de integratie zelf; externe wijzigingen werden gemist omdat de status-poll alleen binaire ingangen las en zuivere uitgangsactoren oversloeg. De status wordt nu ook uit de uitgangsstatus bijgewerkt, via dezelfde gecachte dSS-poll — dus zonder extra belasting van de dS485-bus.

### v4.1.1 (25-06-2026) — Temperatuur & setpoint betrouwbaar na changeover

- **Gemeten temperatuur en setpoint blijven beschikbaar** — voorheen kon de gemeten temperatuur én de doeltemperatuur van een klimaatzone op "onbekend" vallen na een verwarmen/koelen-omschakeling of een herstart, totdat de Thanos-thermostaat zelf een nieuwe waarde stuurde. De integratie leest deze waarden nu uit álle poll-bronnen (de per-zone temperatuurregeling-status, de apartement-sensoruitlezing en de apparaat-temperatuursensoren in de zone) en niet meer alleen uit gepushte events. De climate-entiteit en de temperatuursensoren tonen daardoor direct weer een waarde.

### v4.1.0 (23-06-2026) — Bestendig tegen firmware-updates

- **Automatische herauthenticatie** — wordt het dSS app-token ongeldig (gebruikelijk na een dSS firmware-update), dan toont Home Assistant nu een melding *"Herauthenticatie vereist"* in plaats van stil te falen bij setup. Een nieuw token goedkeuren behoudt de entry, Pro-licentie én alle entiteiten — opnieuw koppelen is niet nodig.
- **Verbindingsfouten worden opnieuw geprobeerd** — een tijdelijke verbindingsfout geeft nu `ConfigEntryNotReady` (HA probeert automatisch opnieuw) in plaats van permanent te falen.
- **Periodieke Pro-licentie-hercheck** — de licentie wordt elke 6 uur opnieuw gevalideerd, zodat een server-side herbinding (na een firmware-id-flip) wordt opgepikt zonder HA-herstart; een Free⇄Pro-wijziging herlaadt de entry automatisch.
- **Repair-melding "Pro-licentie inactief"** — is een Pro-key ingesteld maar valideert deze niet meer, dan verschijnt een duidelijke melding (verdwijnt zodra weer geldig), zodat verdwenen Pro-functies niet langer stil zijn.
- **README** — sectie "Na een dSS firmware-update (1.19.13)" toegevoegd met aandachtspunten (vast IP aanbevolen, reauth, server-side herbinding licentie).

### v4.0.2 (19-06-2026) — dSM12-bemetering ondersteund

- **dSM12 meegenomen in stroomkring-metering** — dSM12-meters leveren nu vermogen (W) en cumulatieve energie (Wh), net als dSM20/dSM25. Alleen de end-of-life dSM11 wordt overgeslagen. Eerdere versies sloten dSM12 uit; dit is geverifieerd op een dSM12-only installatie. De energie-corruptie die eerder speelde kwam van `getSensorValue2`-bus-starvation, die apart is opgelost (vermogen per apparaat is event-only), dus dSM12-metering is veilig.

### v4.0.0 (12-06-2026) — Systeemscenes, robuuste metering & omgevingsstatussen

- **Systeem-alarmscenes als schakelaars** — Brand en Alarm 1-4 krijgen nu een schakelaar (naast de alleen-lezen status-binarysensor) die de scene activeert via `apartment/callScene`. Elke schakelaar leest de echte dSS-status terug en springt vanzelf terug naar uit als de dSS de scene negeert.
- **Omgevingsstatussen (Gratis)** — Dag/Nacht, Schemering, Daglicht en Vakantie als alleen-lezen binarysensoren.
- **Beweging per zone + storing/service (Pro)** — bewegings-binarysensoren per zone, plus geaggregeerde storing- en servicediagnose.
- **Weerdienst (Pro)** — stationsloze buitentemperatuur en zonpositie uit de dSS-weerdienst.
- **Metering herzien** — sensoren voor vermogen (W) en energie (Wh) per apparaat zijn verwijderd: het pollen ervan hongerde de dSM-meetcontroller uit en beschadigde de dSM-energiewaarden. Vermogen en energie worden nu alleen op dSM-(stroomkring-)niveau gelezen. Vermogen per apparaat is event-gestuurd, wordt nooit gepolld.
- **Betrouwbaarheid** — herconfiguratie bij IP-wijziging + DHCP-detectie, snellere niet-blokkerende start, en een geharde event-loop (één afwijkend event kan de loop niet meer stoppen). Woning-systeemstatussen (brand/regen/vorst/hagel/wind/alarm) zijn alleen-lezen waar de dSS schrijven weigert.

### v3.0.0 (12-05-2026) — Grote release

- **Energie-dashboard** — cumulatieve kWh per dSM (`state_class=total_increasing`) + woningbrede kWh-sensor
- **dSS Configurator-entiteiten** — gebruikersgedefinieerde acties → HA-knoppen; gebruikersgedefinieerde statussen → binarysensor/sensor; klokken/timers → run-once-knoppen
- **Per-component-status** — elk uitvoer-apparaat krijgt een diagnostische binarysensor uit `apartment/getDevices` (geen extra busverkeer)
- **Hardening** (uit GPT-4o code-review) — robuustere foutafhandeling in de request-laag en event-listener

### v2.5.0 (14-03-2026)
- **Alarm-entiteiten** — alarm 1-4, paniek, deurbel als schakelaars
- **Aanwezigheidsdetectie** — aanwezig, afwezig, slapen, ontwaken, stand-by, deep off

### v2.4.0 (13-03-2026)
- **Energiemonitoring per dSM** naar Gratis — elke dSM-meter krijgt een eigen apparaat met vermogenssensor
- **Sensorbetrouwbaarheid** — gebruikt de dSS-zone-API voor voorgeschaalde waarden

### v2.2.0 (11-03-2026)
- **Gratis/Pro-split** met licentiesleutelsysteem ([wooniot.nl/pro](https://wooniot.nl/pro))
- **Individuele Joker-schakelaars**, **Joker-binarysensoren**, **apparaatsensoren** (Ulux)
- **Klimaatregeling** (Pro), **buitenweersensoren** (Pro), **scene-detectie** met gebruikersnamen

### v1.0.0 (10-03-2026)
- Eerste release: zone-gebaseerde verlichting, rolluiken, scenes, temperatuursensoren, energiemonitoring
- Event-gestuurde architectuur met realtime status-updates

> Het volledige wijzigingslog (alle tussenversies) staat in de Engelstalige [README.md](README.md#changelog).

## Privacy & Telemetrie

Deze integratie stuurt een minimale anonieme ping naar WoonIoT, eenmalig bij het opstarten en elke 24 uur. Dit helpt ons te begrijpen hoeveel installaties actief zijn en welke HA-versies in gebruik zijn.

**Wat wordt verstuurd:**

| Veld | Waarde | Persoonlijk? |
|------|--------|--------------|
| `v` | Integratieversie | Nee |
| `ha` | Home Assistant-versie | Nee |
| `zones` | Aantal zones (geheel getal) | Nee |
| `devices` | Aantal apparaten (geheel getal) | Nee |
| `dss_id` | Eerste 8 tekens van het dSS-machine-ID | Pseudoniem |
| `pro` | Pro-licentie actief (true/false) | Nee |

De ontvangende server is `ha-ds.internetist.nl` (beheerd door Woon IoT BV, gehost in de EU). Je IP-adres wordt technisch door de server ontvangen als onderdeel van elk HTTP-verzoek. Er worden geen gegevens verkocht of gedeeld met derden. Volledige details: [wooniot.nl/privacy](https://www.wooniot.nl/privacy)

**Afmelden:** Ga naar **Instellingen → Apparaten & Diensten → Digital Strom Smart → Configureren** en schakel de optie *Anonieme telemetrie versturen* uit. Na opslaan wordt er niets meer verstuurd.

> Let op: proeflicenties vereisen ingeschakelde telemetrie. Betaalde Pro-licenties werken zonder telemetrie.

## Over

Ontwikkeld door **[Woon IoT BV](https://wooniot.nl)** — professionele Digital Strom-installateurs en smarthome-specialisten in Nederland.

- Website: [wooniot.nl](https://wooniot.nl)
- Pro-licentie: [wooniot.nl/pro](https://wooniot.nl/pro)
- Problemen melden: [GitHub Issues](https://github.com/wooniot/ha-digitalstrom-smart/issues)
- Licentie: [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/) — gratis voor persoonlijk gebruik, commercieel gebruik vereist schriftelijke toestemming van Woon IoT BV
