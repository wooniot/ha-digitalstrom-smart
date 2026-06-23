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
    CONF_PRO_LICENSE,
)
from .coordinator import DigitalStromCoordinator
from .license import check_pro_license as _check_pro_license, sync_pro_issue

# Pre-import all platform modules to avoid blocking imports in event loop (HA 2026+)
from . import (  # noqa: F401
    light, cover, sensor, scene, switch, climate, binary_sensor, select, button,
)

_LOGGER = logging.getLogger(__name__)


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

    # Create coordinator
    dss_id = entry.data.get(CONF_DSS_ID, "")
    coordinator = DigitalStromCoordinator(hass, api, structure, dss_id=dss_id)

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

    # Fetch scene names (best-effort, don't block setup)
    try:
        await coordinator.fetch_scene_names()
    except Exception as err:
        _LOGGER.warning("Scene name fetch failed (non-fatal): %s", err)

    # Fetch initial states (best-effort)
    try:
        await coordinator.fetch_initial_states()
    except Exception as err:
        _LOGGER.warning("Initial state fetch failed (non-fatal): %s", err)

    # Fetch device sensor values (Ulux etc.) - initial load, then polled + events
    try:
        await coordinator.fetch_device_sensors()
    except Exception as err:
        _LOGGER.warning("Device sensor fetch failed (non-fatal): %s", err)

    # One-time startup poll for per-device power/energy (SW-KL200 etc.)
    # After this, deviceSensorValue events keep values current.
    try:
        await coordinator.fetch_device_power_sensors()
    except Exception as err:
        _LOGGER.warning("Device power sensor fetch failed (non-fatal): %s", err)

    # Fetch per-circuit (dSM) power + cumulative energy
    try:
        await coordinator.fetch_circuit_data()
    except Exception as err:
        _LOGGER.warning("Circuit data fetch failed (non-fatal): %s", err)

    # Fetch User Defined Actions and States (free, apartment-level)
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

    # Fetch initial apartment presence state (free + pro — one cheap API call)
    try:
        await coordinator.fetch_apartment_state()
    except Exception as err:
        _LOGGER.debug("Apartment state fetch failed (non-fatal): %s", err)

    # Pro: fetch climate and sensor data
    if coordinator.pro_enabled:
        try:
            await coordinator.fetch_climate_data()
        except Exception as err:
            _LOGGER.warning("Climate data fetch failed (non-fatal): %s", err)
        try:
            await coordinator.fetch_sensor_data()
        except Exception as err:
            _LOGGER.warning("Sensor data fetch failed (non-fatal): %s", err)

        # Log detected climate zones for diagnostics
        climate_zones = [
            (zid, zi["name"]) for zid, zi in coordinator.zones.items()
            if coordinator.has_temp_control(zid)
        ]
        if climate_zones:
            _LOGGER.info(
                "Climate zones detected: %s",
                ", ".join(f"{name} (zone {zid})" for zid, name in climate_zones),
            )
        else:
            _LOGGER.warning("No climate zones detected — check dSS temperature control config")

    # Start event listener as background task (must not block HA bootstrap)
    entry.async_create_background_task(
        hass, coordinator.start_event_listener(),
        f"{DOMAIN}_event_listener",
    )

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

    # Forward to platforms
    platforms = list(PLATFORMS_FREE)
    if coordinator.pro_enabled:
        platforms.extend(PLATFORMS_PRO)
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

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
        for entry_data in hass.data[DOMAIN].values():
            try:
                await entry_data["api"].call_scene(zone_id, group, scene)
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
