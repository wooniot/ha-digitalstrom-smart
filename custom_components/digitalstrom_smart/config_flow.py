"""Config flow for digitalSTROM Smart integration."""

import asyncio
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .api import DigitalStromApi, DigitalStromApiError, DigitalStromAuthError
from .const import (
    DOMAIN,
    CONN_LOCAL,
    CONN_CLOUD,
    CONF_CONNECTION_TYPE,
    CONF_APP_TOKEN,
    CONF_CLOUD_URL,
    CONF_CLOUD_USER,
    CONF_CLOUD_PASS,
    CONF_ENABLED_ZONES,
    CONF_DSS_ID,
    CONF_INVERT_COVER,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CONNECTION_TYPE, default=CONN_LOCAL): vol.In(
            {CONN_LOCAL: "Local (IP address)", CONN_CLOUD: "Cloud (*.digitalstrom.net)"}
        ),
    }
)

STEP_LOCAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="192.168.1.x"): str,
        vol.Required(CONF_PORT, default=8080): int,
    }
)

STEP_CLOUD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLOUD_URL): str,
        vol.Required(CONF_CLOUD_USER, default="dssadmin"): str,
        vol.Required(CONF_CLOUD_PASS): str,
    }
)


class DigitalStromSmartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for digitalSTROM Smart."""

    VERSION = 1

    def __init__(self) -> None:
        self._api: DigitalStromApi | None = None
        self._pending_token: str | None = None
        self._connection_type: str | None = None
        self._data: dict = {}
        self._zones: dict[int, str] = {}

    async def async_step_user(self, user_input=None):
        """Step 1: Choose local or cloud connection."""
        if user_input is not None:
            self._connection_type = user_input[CONF_CONNECTION_TYPE]
            if self._connection_type == CONN_LOCAL:
                return await self.async_step_local()
            return await self.async_step_cloud()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)

    async def async_step_local(self, user_input=None):
        """Step 2a: Local connection - enter IP and request app token."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            self._api = DigitalStromApi(host=host, port=port)
            self._data = {
                CONF_CONNECTION_TYPE: CONN_LOCAL,
                CONF_HOST: host,
                CONF_PORT: port,
            }

            try:
                self._pending_token = await self._api.request_app_token()
                return await self.async_step_approve_token()
            except DigitalStromApiError as err:
                _LOGGER.error("Connection failed: %s", err)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="local",
            data_schema=STEP_LOCAL_SCHEMA,
            errors=errors,
        )

    async def async_step_approve_token(self, user_input=None):
        """Step 2a-2: Wait for user to press meter button."""
        errors = {}

        if user_input is not None:
            # Check if token was approved
            approved = await self._api.check_app_token(self._pending_token)
            if approved:
                self._data[CONF_APP_TOKEN] = self._pending_token
                return await self._finish_setup()
            errors["base"] = "token_not_approved"

        return self.async_show_form(
            step_id="approve_token",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={
                "token": self._pending_token[:20] + "..." if self._pending_token else ""
            },
        )

    async def async_step_cloud(self, user_input=None):
        """Step 2b: Cloud connection."""
        errors = {}

        if user_input is not None:
            cloud_url = user_input[CONF_CLOUD_URL].rstrip("/")
            if not cloud_url.startswith("https://"):
                cloud_url = f"https://{cloud_url}"

            self._api = DigitalStromApi(
                host="",
                cloud_url=cloud_url,
                cloud_user=user_input[CONF_CLOUD_USER],
                cloud_pass=user_input[CONF_CLOUD_PASS],
            )
            self._data = {
                CONF_CONNECTION_TYPE: CONN_CLOUD,
                CONF_CLOUD_URL: cloud_url,
                CONF_CLOUD_USER: user_input[CONF_CLOUD_USER],
                CONF_CLOUD_PASS: user_input[CONF_CLOUD_PASS],
            }

            try:
                await self._api.connect()
                return await self._finish_setup()
            except DigitalStromAuthError:
                errors["base"] = "invalid_auth"
            except DigitalStromApiError:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="cloud",
            data_schema=STEP_CLOUD_SCHEMA,
            errors=errors,
        )

    async def _finish_setup(self):
        """Get structure and create entry."""
        try:
            version = await self._api.get_version()
            structure = await self._api.get_structure()

            apartment = structure.get("apartment", structure)
            zones = apartment.get("zones", [])

            # Get dSS unique identifier
            dss_id = version.get("dSUID", "") or version.get("MachineID", "")
            if not dss_id:
                # Fallback: use host or cloud URL as identifier
                dss_id = self._data.get(CONF_HOST, "") or self._data.get(CONF_CLOUD_URL, "")
            self._data[CONF_DSS_ID] = dss_id

            # Prevent duplicate entries for same dSS
            await self.async_set_unique_id(dss_id)
            self._abort_if_unique_id_configured()

            # Collect zone IDs (skip zone 0 = apartment level, 65534 = unassigned)
            zone_ids = []
            for z in zones:
                zid = z.get("id", 0)
                if zid == 0 or zid >= 65534:
                    continue
                zone_ids.append(zid)

            self._data[CONF_ENABLED_ZONES] = zone_ids

            title = f"dSS {version.get('distroVersion', 'Unknown')}"

            await self._api.close()
            return self.async_create_entry(title=title, data=self._data)

        except DigitalStromApiError as err:
            await self._api.close()
            return self.async_abort(reason="cannot_connect")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DigitalStromOptionsFlow(config_entry)


class DigitalStromOptionsFlow(config_entries.OptionsFlow):
    """Handle options for digitalSTROM Smart."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage zones and options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        coordinator = self.hass.data.get(DOMAIN, {}).get(
            self._config_entry.entry_id, {}
        ).get("coordinator")

        zone_options = {}
        if coordinator:
            for zone_id, zone_info in coordinator.zones.items():
                zone_options[zone_id] = f"{zone_info['name']} ({zone_info['device_count']} devices)"

        current_enabled = self._config_entry.data.get(CONF_ENABLED_ZONES, [])
        current_invert = self._config_entry.options.get(CONF_INVERT_COVER, False)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENABLED_ZONES,
                    default=current_enabled,
                ): vol.All(
                    vol.Coerce(list),
                    [vol.In(zone_options)],
                ),
                vol.Optional(
                    CONF_INVERT_COVER,
                    default=current_invert,
                ): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
