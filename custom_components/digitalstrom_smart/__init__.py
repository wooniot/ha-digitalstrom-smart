"""Digital Strom Smart integration for Home Assistant.

The definitive Digital Strom integration - zone-based, event-driven,
scenes as primary control. Minimal bus load.

Free tier: lights, covers, scenes, sensors (zone + device), switches (joker), per-dSM energy
Pro tier: climate, outdoor sensors, rain detection, device blink

Developed by Woon IoT BV - https://wooniot.nl
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import DigitalStromApi, DigitalStromApiError, DigitalStromAuthError
from .const import (
    DOMAIN,
    PLATFORMS_FREE,
    PLATFORMS_PRO,
    CONF_APP_TOKEN,
    CONF_DSS_ID,
    CONF_ENABLED_ZONES,
    CONF_PRO_LICENSE,
    CONF_MAIN_POLL_INTERVAL,
    CONF_BINARY_POLL_INTERVAL,
    CONF_EXTRA_VENTILATION_DSUIDS,
    DEFAULT_MAIN_POLL_INTERVAL,
    DEFAULT_BINARY_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
)
from .coordinator import DigitalStromCoordinator
from .license import check_pro_license as _check_pro_license, sync_pro_issue

# Pre-import all platform modules to avoid blocking imports in event loop (HA 2026+)
from . import (  # noqa: F401
    light, cover, sensor, scene, switch, climate, binary_sensor, select, button, event,
)

_LOGGER = logging.getLogger(__name__)


def _clamp_interval(value) -> int:
    """Clamp a user-supplied poll interval to the safe range.

    A malformed or out-of-range option must never brick setup or hammer the
    dSS; fall back to the default and keep it within [MIN, MAX].
    """
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAIN_POLL_INTERVAL
    return max(MIN_POLL_INTERVAL, min(MAX_POLL_INTERVAL, seconds))


async def _async_reload_on_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry after its options were updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Digital Strom Smart from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create API client (local connection only)
    api = DigitalStromApi(
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, 8080),
        app_token=entry.data[CONF_APP_TOKEN],
    )

    # Connect. Distinguish a dead/invalid app token (→ reauth) from a plain
    # connection failure (→ retry). A dSS firmware update can invalidate the
    # stored app token; without this split HA would just keep failing setup.
    try:
        await api.connect()
    except DigitalStromAuthError as err:
        await api.close()
        _LOGGER.warning("dSS app token rejected — re-authentication required: %s", err)
        raise ConfigEntryAuthFailed(
            "Digital Strom app token is no longer valid (often after a dSS "
            "firmware update). Please re-authorise a new token in the dSS."
        ) from err
    except DigitalStromApiError as err:
        await api.close()
        raise ConfigEntryNotReady(f"Cannot connect to dSS at {entry.data[CONF_HOST]}: {err}") from err

    # Get structure
    try:
        structure = await api.get_structure()
    except DigitalStromAuthError as err:
        await api.close()
        _LOGGER.warning("dSS rejected token while reading structure: %s", err)
        raise ConfigEntryAuthFailed(
            "Digital Strom app token is no longer valid. Please re-authorise."
        ) from err
    except DigitalStromApiError as err:
        await api.close()
        raise ConfigEntryNotReady(f"Cannot read structure from dSS: {err}") from err

    # Auto-enable zones created in the dSS after initial setup (#28).
    # CONF_ENABLED_ZONES is a snapshot taken at first setup; a zone added later
    # is not in that list, so the platforms filter it out and a plain reload
    # never shows the new room. Merge any newly discovered zone ids into the
    # enabled list here, before the platforms are set up. An empty list already
    # means "all zones enabled", so only top up a non-empty (subset) list.
    enabled_zones = list(entry.data.get(CONF_ENABLED_ZONES, []))
    if enabled_zones:
        apartment = structure.get("apartment", structure)
        all_zone_ids = [
            z.get("id", 0)
            for z in apartment.get("zones", [])
            if 0 < z.get("id", 0) < 65534
        ]
        new_zones = [z for z in all_zone_ids if z not in enabled_zones]
        if new_zones:
            _LOGGER.info(
                "Discovered %d new dSS zone(s) since setup, enabling them: %s",
                len(new_zones), new_zones,
            )
            hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_ENABLED_ZONES: enabled_zones + new_zones},
            )

    # Create coordinator. Poll intervals are user-tunable (Options flow) so a
    # large install can throttle the dSS request rate; both are clamped to a
    # safe range and fall back to the defaults.
    dss_id = entry.data.get(CONF_DSS_ID, "")
    main_interval = _clamp_interval(
        entry.options.get(CONF_MAIN_POLL_INTERVAL, DEFAULT_MAIN_POLL_INTERVAL)
    )
    binary_interval = _clamp_interval(
        entry.options.get(CONF_BINARY_POLL_INTERVAL, DEFAULT_BINARY_POLL_INTERVAL)
    )
    coordinator = DigitalStromCoordinator(
        hass, api, structure, dss_id=dss_id,
        main_poll_interval=main_interval,
        binary_poll_interval=binary_interval,
    )

    # Opt-in: UMR200 ventilation outputs configured outside the dS Ventilation
    # colour group (e.g. Joker/black). Parse the CSV option into a lowercased
    # set so get_umr200_devices() admits them regardless of colour group. Must
    # be set BEFORE the first refresh so the initial ventilation poll includes
    # them. Empty by default → strict group gate unchanged.
    raw_extra = entry.options.get(CONF_EXTRA_VENTILATION_DSUIDS, "") or ""
    coordinator.extra_ventilation_dsuids = {
        d.strip().lower() for d in raw_extra.replace("\n", ",").split(",") if d.strip()
    }
    if coordinator.extra_ventilation_dsuids:
        _LOGGER.info(
            "Extra ventilation UMR200 dsuids (opt-in, outside Ventilation group): %s",
            ", ".join(sorted(coordinator.extra_ventilation_dsuids)),
        )

    # Check Pro license. Store the key + entry id on the coordinator so it can
    # re-validate periodically (picks up a server-side rebind without a restart).
    pro_key = entry.options.get(CONF_PRO_LICENSE, "")
    coordinator.pro_license_key = pro_key
    coordinator.entry_id = entry.entry_id
    if pro_key:
        license_result = await _check_pro_license(pro_key, dss_id)
        coordinator.pro_enabled = license_result["valid"]
        coordinator.license_info = license_result
        if coordinator.pro_enabled:
            _LOGGER.info("Digital Strom Pro features enabled")
        else:
            _LOGGER.warning(
                "Pro license invalid: reason=%s, dss_id_sent=%s, method=%s",
                license_result.get("reason"), license_result.get("dss_id_sent"),
                license_result.get("method"),
            )
    else:
        coordinator.license_info = {"valid": False, "reason": "no_key", "type": None, "method": None}

    # Surface a repair issue if a Pro key is set but no longer validates
    # (e.g. license unbound after a firmware update). Cleared when valid.
    sync_pro_issue(hass, entry.entry_id, bool(pro_key), coordinator.pro_enabled)

    # Initial data fetch
    await coordinator.async_config_entry_first_refresh()

    # --- Alleen de uitlezingen die bepalen WELKE entiteiten bestaan, lopen
    # synchroon vóór het forwarden van de platforms. Alle overige (waarde-)
    # uitlezingen gaan naar een achtergrondtaak (zie async_startup_fetches),
    # zodat de setup van de config entry binnen 1-2 min klaar is en HA niet
    # minutenlang "Waiting for integrations to complete setup" toont.
    # (René, 19 okt 2026 — diagnose trage setup bij herstart.)
    #
    # Let op: scènenamen, user actions/states, custom states en timed events
    # worden door de platforms uitgelezen om de BIJBEHORENDE entiteiten AAN TE
    # MAKEN (scene/button/switch/binary_sensor/sensor). Als die pas na het
    # forwarden binnenkomen, ontbreken die entiteiten tot een reload — dus die
    # vier blijven bewust op het kritieke pad. De zware per-(zone,groep) lus in
    # fetch_scene_names is daarom geparallelliseerd i.p.v. verplaatst.

    # Scene names (gates scene entities) — best-effort, geparallelliseerd.
    try:
        await coordinator.fetch_scene_names()
    except Exception as err:
        _LOGGER.warning("Scene name fetch failed (non-fatal): %s", err)

    # User Defined Actions/States + custom states + timed events — bepalen
    # welke button/switch/binary_sensor/sensor-entiteiten bestaan.
    try:
        await coordinator.fetch_user_actions()
    except Exception as err:
        _LOGGER.warning("User actions fetch failed (non-fatal): %s", err)
    try:
        await coordinator.fetch_user_states()
    except Exception as err:
        _LOGGER.warning("User states fetch failed (non-fatal): %s", err)
    try:
        await coordinator.fetch_custom_states()
    except Exception as err:
        _LOGGER.warning("Custom states fetch failed (non-fatal): %s", err)
    try:
        await coordinator.fetch_timed_events()
    except Exception as err:
        _LOGGER.warning("Timed events fetch failed (non-fatal): %s", err)

    # Store
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    # Clean shutdown on HA stop
    async def _shutdown(event):
        await coordinator.shutdown()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _shutdown)
    )

    # Reload the entry when options change so a new poll interval takes effect
    # immediately (no manual HA restart needed).
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))

    # Forward to platforms
    platforms = list(PLATFORMS_FREE)
    if coordinator.pro_enabled:
        platforms.extend(PLATFORMS_PRO)
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    # Best-effort waarde-uitlezingen (zone-scènestand, device-sensoren, per-circuit
    # vermogen, climate) NU op de achtergrond — de entiteiten bestaan al en krijgen
    # hun waarde enkele seconden later (async_startup_fetches port daarna de
    # listeners). Die taak start óók de event-listener, bewust ná de startup-seed,
    # zodat een seed geen vers event overschrijft. Dit haalt de minuten durende
    # seed-lussen van het kritieke setup-pad af (René, 19 okt 2026).
    entry.async_create_background_task(
        hass, coordinator.async_startup_fetches(),
        f"{DOMAIN}_startup_fetches",
    )

    # Register services
    _register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if not data:
        return True

    coordinator = data["coordinator"]
    platforms = list(PLATFORMS_FREE)
    if coordinator.pro_enabled:
        platforms.extend(PLATFORMS_PRO)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.shutdown()

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up the Pro-license repair issue when the entry is removed."""
    sync_pro_issue(hass, entry.entry_id, False, False)


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def handle_call_scene(call: ServiceCall) -> None:
        zone_id = call.data["zone_id"]
        group = call.data.get("group", 1)
        scene = call.data["scene_number"]
        force = call.data.get("force", False)
        for entry_data in hass.data[DOMAIN].values():
            try:
                await entry_data["api"].call_scene(zone_id, group, scene, force=force)
            except DigitalStromApiError as err:
                _LOGGER.error("call_scene failed: %s", err)

    async def handle_blink(call: ServiceCall) -> None:
        """Blink a device for identification. PRO."""
        dsuid = call.data["dsuid"]
        for entry_data in hass.data[DOMAIN].values():
            coordinator = entry_data["coordinator"]
            if not coordinator.pro_enabled:
                _LOGGER.warning("Blink requires Pro license")
                return
            try:
                await entry_data["api"].blink_device(dsuid)
            except DigitalStromApiError as err:
                _LOGGER.error("blink failed: %s", err)

    async def handle_save_scene(call: ServiceCall) -> None:
        """Save current output values as a scene. PRO."""
        zone_id = call.data["zone_id"]
        group = call.data.get("group", 1)
        scene = call.data["scene_number"]
        for entry_data in hass.data[DOMAIN].values():
            coordinator = entry_data["coordinator"]
            if not coordinator.pro_enabled:
                _LOGGER.warning("Save scene requires Pro license")
                return
            try:
                await entry_data["api"].save_scene(zone_id, group, scene)
            except DigitalStromApiError as err:
                _LOGGER.error("save_scene failed: %s", err)

    if not hass.services.has_service(DOMAIN, "call_scene"):
        hass.services.async_register(DOMAIN, "call_scene", handle_call_scene)
        hass.services.async_register(DOMAIN, "blink_device", handle_blink)
        hass.services.async_register(DOMAIN, "save_scene", handle_save_scene)
