
## TODO (23 jun 2026): auto-reauth na firmware/token-verlies
Bij een dSS firmware-update kan (a) het IP wijzigen (DHCP) én (b) de app-token ongeldig worden. Nu: reconfigure leest dan ongeauthenticeerd → krijgt MachineID i.p.v. dSUID → `wrong_device`, integratie blijft setup_error. Geen automatisch herstel. GEVAL Visser 22 jun: hele HVAC-DS lag eruit.
FIX: detecteer auth-failure (dode token) apart van connectie-fout → raise ConfigEntryAuthFailed → HA toont reauth; async_step_reauth vraagt opnieuw inlog, haalt NIEUWE app-token, behoudt unique_id/entities. + DHCP-discovery die bij gewijzigd IP de host automatisch bijwerkt op de bestaande entry (matchen op dSUID via geauth. read). Maakt firmware-updates zelfhelend.

## INCIDENT-ANALYSE Visser 22-23 jun 2026 (firmware 1.19.13) → integratie-verbeterpunten
Eén firmware-update (1.19.12→1.19.13) veroorzaakte een KETTING: (a) nieuw DHCP-IP (.105→.38), (b) app-token ongeldig, (c) **dss_id-flip** (dSUID `12f137…` → MachineID `ed6c32f4…`), (d) daardoor Pro-licentie los. Geen laag ving het op → hele HVAC 26u dood. Re-pairen herstelde het, maar: Pro-sleutel kwijt (zat in entry-options, weg bij delete) + **alle 930 entity-id's gedrift** (verse unique_ids met nieuw id + naamconflicten met de Modbus-`_klimaat`-entities → `_2`-suffixen).

**VOORTGANG (23 jun 2026):**
- ✅ Fix #2 auto-reauth — GEDAAN (commit e3f4e36). __init__ raiset ConfigEntryAuthFailed/NotReady; config_flow heeft async_step_reauth(_confirm); strings EN/NL/DE.
- ✅ README EN/NL/DE firmware-1.19.13 sectie — GEDAAN (commit a201c1f).
- ⏳ Fix #1 (stabiele MAC/serial identifier + migratie) = KERNFIX maar BREAKING op ~930 live entities → vereist (a) geverifieerd dSS MAC-property-pad op echte hardware, (b) async_migrate_entry getest op test-dSS/René vóór release. NIET ongevraagd uitrollen.
- ⏳ Fix #3 DHCP-self-heal-bij-id-flip — hangt af van #1 (stabiele id). async_step_dhcp werkt nu host bij maar matcht op flippend id.
- ✅ Fix #4 periodieke licentie-hercheck — GEDAAN. coordinator._recheck_license elke 6h; pakt server-side rebind op zonder HA-restart; reload bij Free<->Pro-flip. Licentielogica verplaatst naar license.py (geen circular import).
- ✅ Fix #5 resilience — GEDAAN als niet-flapperende repair-issue "Pro-licentie inactief" (alleen wanneer key gezet maar invalid). license.sync_pro_issue; strings issues.pro_license_invalid EN/NL/DE; opgeruimd bij remove_entry.

**FIXES (prioriteit):**
1. **Stabiele identifier** voor unique_ids + config-entry-unique_id + Pro-licentiebinding = **EthernetID/MAC** (bv. a8:99:5c:01:2a:94) of Serial, NIET de dSUID/MachineID (die flippen bij firmware). Mét migratie oud→nieuw. → een firmware-flip wordt dan een non-event (geen entity-drift, geen licentie-loss). DIT IS DE KERNFIX.
2. **Auto-reauth:** dode app-token apart detecteren van connectie-fout → `ConfigEntryAuthFailed` → `async_step_reauth` (nieuwe token aanvragen, entry/entities/options/licentie behouden). Geen delete+re-pair meer nodig.
3. **DHCP-self-heal die de id-flip overleeft:** match de discovered dSS op het stabiele MAC/serial (niet op het flippende id) → werk alleen de host bij op de bestaande entry. Lost de IP-helft automatisch op.
4. **Pro-sleutel + options bewaren** bij re-pair/reconfigure (nu verloren bij delete → Free). En **licentie-hercheck bij config-entry-reload** (nu alleen bij setup/HA-restart → een herbind werd pas na restart opgepikt).
5. **Resilience/alert:** als de integratie >X min `setup_error` of >X% entities unavailable is → repair-issue/notificatie (nu ontdekt via "het is te warm", niet via monitoring).

**SERVER-SIDE (telemetry/license, Hetzner):** detecteer dss_id-flip in de pings (identieke zones/devices/MAC-vingerafdruk onder nieuw id, pro=0) → AUTO-herbind of alert i.p.v. de klant op Free zetten. Server-side tegenhanger van fix #1.

**README (EN/NL/DE) — sectie "Na een dSS firmware-update (bv. 1.19.13)":** IP kan wijzigen → **DHCP-reservering/statisch IP aanraden**; app-token kan ongeldig worden → re-pair/reauth (token accorderen in dSS-admin); dss_id kan flippen → Pro wordt server-side herbonden (contact support). Tip: statisch IP voorkomt de helft.
