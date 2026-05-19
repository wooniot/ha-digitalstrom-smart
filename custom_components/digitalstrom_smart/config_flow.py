"""Config flow for Digital Strom Smart integration."""

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .api import DigitalStromApi, DigitalStromApiError
from .const import (
    DOMAIN,
    CONN_LOCAL,
    CONF_CONNECTION_TYPE,
    CONF_APP_TOKEN,
    CONF_ENABLED_ZONES,
    CONF_DSS_ID,
    CONF_INVERT_COVER,
    CONF_PRO_LICENSE,
)

_LOGGER = logging.getLogger(__name__)

STEP_LOCAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="192.168.1.x"): str,
        vol.Required(CONF_PORT, default=8080): int,
    }
)


class DigitalStromSmartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Digital Strom Smart."""

    VERSION = 1

    def __init__(self) -> None:
        self._api: DigitalStromApi | None = None
        self._pending_token: str | None = None
        self._data: dict = {}

    async def async_step_user(self, user_input=None):
        """Step 1: Enter dSS IP address and port."""
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
            step_id="user",
            data_schema=STEP_LOCAL_SCHEMA,
            errors=errors,
        )

    async def async_step_approve_token(self, user_input=None):
        """Step 2: Wait for user to approve token in dSS admin."""
        errors = {}

        if user_input is not None:
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
                dss_id = self._data.get(CONF_HOST, "")
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

        except DigitalStromApiError:
            await self._api.close()
            return self.async_abort(reason="cannot_connect")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DigitalStromOptionsFlow()


class DigitalStromOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Digital Strom Smart."""

    async def async_step_init(self, user_input=None):
        """Manage zones and options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        entry = self.config_entry

        coordinator = self.hass.data.get(DOMAIN, {}).get(
            entry.entry_id, {}
        ).get("coordinator")

        zone_options = {}
        if coordinator:
            for zone_id, zone_info in coordinator.zones.items():
                zone_options[str(zone_id)] = f"{zone_info['name']} ({zone_info['device_count']} devices)"

        current_enabled = [str(z) for z in entry.data.get(CONF_ENABLED_ZONES, [])]
        current_invert = entry.options.get(CONF_INVERT_COVER, False)
        current_pro = entry.options.get(CONF_PRO_LICENSE, "")

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_INVERT_COVER,
                    default=current_invert,
                ): bool,
                vol.Optional(
                    CONF_PRO_LICENSE,
                    default=current_pro,
                ): str,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
