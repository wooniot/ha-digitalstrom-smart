"""digitalSTROM Smart integration for Home Assistant.

Zone-based, event-driven integration that uses scenes as primary control.
Minimal bus load compared to traditional per-device polling.
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall

from .api import DigitalStromApi, DigitalStromApiError
from .const import (
    DOMAIN,
    PLATFORMS,
    CONN_CLOUD,
    CONF_CONNECTION_TYPE,
    CONF_APP_TOKEN,
    CONF_CLOUD_URL,
    CONF_CLOUD_USER,
    CONF_CLOUD_PASS,
    CONF_DSS_ID,
)
from .coordinator import DigitalStromCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up digitalSTROM Smart from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create API client
    if entry.data.get(CONF_CONNECTION_TYPE) == CONN_CLOUD:
        api = DigitalStromApi(
            host="",
            cloud_url=entry.data[CONF_CLOUD_URL],
            cloud_user=entry.data[CONF_CLOUD_USER],
            cloud_pass=entry.data[CONF_CLOUD_PASS],
        )
    else:
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

    # Initial data fetch
    await coordinator.async_config_entry_first_refresh()

    # Fetch scene names from dSS (user-defined names like "Dag", "Avond" etc.)
    await coordinator.fetch_scene_names()

    # Start event listener (don't await - it long-polls and would block startup)
    hass.async_create_task(coordinator.start_event_listener())

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
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    _register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator = data["coordinator"]
        await coordinator.shutdown()

    return unload_ok


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def handle_call_scene(call: ServiceCall) -> None:
        """Handle call_scene service."""
        zone_id = call.data["zone_id"]
        group = call.data.get("group", 1)
        scene = call.data["scene_number"]

        for entry_data in hass.data[DOMAIN].values():
            api = entry_data["api"]
            try:
                await api.call_scene(zone_id, group, scene)
            except DigitalStromApiError as err:
                _LOGGER.error("call_scene failed: %s", err)

    async def handle_pause(call: ServiceCall) -> None:
        """Handle pause service."""
        for entry_data in hass.data[DOMAIN].values():
            coordinator = entry_data["coordinator"]
            await coordinator.pause()

    async def handle_resume(call: ServiceCall) -> None:
        """Handle resume service."""
        for entry_data in hass.data[DOMAIN].values():
            coordinator = entry_data["coordinator"]
            await coordinator.resume()

    if not hass.services.has_service(DOMAIN, "call_scene"):
        hass.services.async_register(DOMAIN, "call_scene", handle_call_scene)
        hass.services.async_register(DOMAIN, "pause", handle_pause)
        hass.services.async_register(DOMAIN, "resume", handle_resume)
