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

from .api import DigitalStromApi, DigitalStromApiError
from .const import (
    DOMAIN,
    PLATFORMS_FREE,
    PLATFORMS_PRO,
    CONF_APP_TOKEN,
    CONF_DSS_ID,
    CONF_PRO_LICENSE,
)
from .coordinator import DigitalStromCoordinator

# Pre-import all platform modules to avoid blocking imports in event loop (HA 2026+)
from . import (  # noqa: F401
    light, cover, sensor, scene, switch, climate, binary_sensor, select,
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

    # Connect
    try:
        await api.connect()
    except DigitalStromApiError as err:
        _LOGGER.error("Failed to connect to dSS: %s", err)
        await api.close()
        return False

    # Get structure
    try:
        structure = await api.get_structure()
    except DigitalStromApiError as err:
        _LOGGER.error("Failed to get structure: %s", err)
        await api.close()
        return False

    # Create coordinator
    dss_id = entry.data.get(CONF_DSS_ID, "")
    coordinator = DigitalStromCoordinator(hass, api, structure, dss_id=dss_id)

    # Check Pro license
    pro_key = entry.options.get(CONF_PRO_LICENSE, "")
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

    # Fetch per-circuit (dSM) power data
    try:
        await coordinator.fetch_circuit_data()
    except Exception as err:
        _LOGGER.warning("Circuit data fetch failed (non-fatal): %s", err)

    # Pro: fetch climate, sensor, and apartment state data
    if coordinator.pro_enabled:
        try:
            await coordinator.fetch_climate_data()
            await coordinator.fetch_sensor_data()
            await coordinator.fetch_apartment_state()
        except Exception as err:
            _LOGGER.warning("Pro data fetch failed (non-fatal): %s", err)

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


async def _check_pro_license(key: str, dss_id: str) -> dict:
    """Validate Pro license key with WoonIoT server.

    Returns dict with: valid, reason, type, method (online/offline).
    """
    if not key:
        return {"valid": False, "reason": "no_key", "type": None, "method": None}
    dss_short = dss_id[:8] if dss_id else ""
    try:
        from .const import PRO_LICENSE_URL
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                PRO_LICENSE_URL,
                json={"key": key, "dss_id": dss_short},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "valid": data.get("valid", False),
                        "reason": data.get("reason", "ok" if data.get("valid") else "unknown"),
                        "type": data.get("type"),
                        "method": "online",
                        "dss_id_sent": dss_short,
                    }
    except Exception:
        pass
    # Offline fallback: verify HMAC signature of key
    valid = _verify_key_offline(key)
    return {
        "valid": valid,
        "reason": "ok" if valid else "invalid_signature",
        "type": "offline",
        "method": "offline",
        "dss_id_sent": dss_short,
    }


def _verify_key_offline(key: str) -> bool:
    """Verify license key HMAC signature for offline validation."""
    import hashlib
    import hmac as _hmac
    parts = key.split("-")
    if len(parts) != 4:
        return False
    prefix = parts[0]
    if prefix not in ("PRO", "TRIAL"):
        return False
    body = f"{prefix}-{parts[1]}-{parts[2]}"
    # Signing key (split to discourage casual extraction)
    _k = "wooniot" + "-ds-" + "pro-2026" + "-secret" + "-key"
    sig = _hmac.new(
        _k.encode(), body.encode(), hashlib.sha256
    ).hexdigest()[:4].upper()
    return parts[3] == sig


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
