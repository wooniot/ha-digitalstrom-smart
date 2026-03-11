"""Digital Strom Smart integration for Home Assistant.

The definitive Digital Strom integration - zone-based, event-driven,
scenes as primary control. Minimal bus load.

Free tier: lights, covers, scenes, basic sensors, pause/resume
Pro tier: climate, energy dashboard, outdoor sensors, device blink, smooth dimming

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
    light, cover, sensor, scene, switch, climate, binary_sensor,
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
        coordinator.pro_enabled = await _check_pro_license(pro_key, dss_id)
        if coordinator.pro_enabled:
            _LOGGER.info("Digital Strom Pro features enabled")

    # Initial data fetch
    await coordinator.async_config_entry_first_refresh()

    # Fetch scene names and initial states (best-effort, don't block setup)
    try:
        await coordinator.fetch_scene_names()
    except Exception as err:
        _LOGGER.warning("Scene name fetch failed (non-fatal): %s", err)

    try:
        await coordinator.fetch_initial_states()
    except Exception as err:
        _LOGGER.warning("Initial state fetch failed (non-fatal): %s", err)

    # Pro: fetch climate and sensor data
    if coordinator.pro_enabled:
        try:
            await coordinator.fetch_climate_data()
            await coordinator.fetch_sensor_data()
            await coordinator.fetch_circuit_data()
        except Exception as err:
            _LOGGER.warning("Pro data fetch failed (non-fatal): %s", err)

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


async def _check_pro_license(key: str, dss_id: str) -> bool:
    """Validate Pro license key with WoonIoT server."""
    if not key:
        return False
    try:
        from .const import PRO_LICENSE_URL
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                PRO_LICENSE_URL,
                json={"key": key, "dss_id": dss_id[:8] if dss_id else ""},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("valid", False)
    except Exception:
        pass
    # Offline fallback: accept keys starting with "PRO-"
    return key.startswith("PRO-") and len(key) >= 20


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

    async def handle_pause(call: ServiceCall) -> None:
        for entry_data in hass.data[DOMAIN].values():
            await entry_data["coordinator"].pause()

    async def handle_resume(call: ServiceCall) -> None:
        for entry_data in hass.data[DOMAIN].values():
            await entry_data["coordinator"].resume()

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
        hass.services.async_register(DOMAIN, "pause", handle_pause)
        hass.services.async_register(DOMAIN, "resume", handle_resume)
        hass.services.async_register(DOMAIN, "blink_device", handle_blink)
        hass.services.async_register(DOMAIN, "save_scene", handle_save_scene)
