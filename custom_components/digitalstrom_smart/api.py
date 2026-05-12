"""Async API client for Digital Strom Server (dSS).

Complete JSON API coverage - the definitive dSS client for Home Assistant.
Developed by Woon IoT BV - https://wooniot.nl
"""

import asyncio
import hashlib
import logging
import os
import re
import ssl
from typing import Any

import aiohttp
from yarl import URL

from .const import EVENT_SUBSCRIPTION_ID, EVENT_POLL_TIMEOUT, DSS_APP_NAME

_LOGGER = logging.getLogger(__name__)

# Nonce counter for Digest auth (must increment per request)
_nc_counter = 0


class DigitalStromApiError(Exception):
    """General API error."""


class DigitalStromAuthError(DigitalStromApiError):
    """Authentication error."""


def _build_digest_header(
    username: str, password: str, method: str, uri: str,
    realm: str, nonce: str, qop: str = "",
) -> str:
    """Build HTTP Digest Authorization header value."""
    global _nc_counter
    _nc_counter += 1

    ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()

    if qop:
        nc = f"{_nc_counter:08d}"
        cnonce = hashlib.md5(os.urandom(8)).hexdigest()[:16]
        response = hashlib.md5(
            f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}".encode()
        ).hexdigest()
        return (
            f'Digest username="{username}", realm="{realm}", nonce="{nonce}", '
            f'uri="{uri}", qop={qop}, nc={nc}, cnonce="{cnonce}", '
            f'response="{response}"'
        )

    response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
    return (
        f'Digest username="{username}", realm="{realm}", nonce="{nonce}", '
        f'uri="{uri}", response="{response}"'
    )


def _parse_www_authenticate(header: str) -> dict:
    """Parse WWW-Authenticate Digest header into dict."""
    result = {}
    for match in re.finditer(r'(\w+)="([^"]*)"', header):
        result[match.group(1)] = match.group(2)
    return result


class DigitalStromApi:
    """Async client for dSS JSON API.

    Supports both local (application token) and cloud (HTTP Digest + CSRF) auth.
    Full API coverage: zones, devices, metering, climate, scenes, events.
    Developed by Woon IoT BV.
    """

    def __init__(
        self,
        host: str,
        port: int = 8080,
        app_token: str | None = None,
        cloud_url: str | None = None,
        cloud_user: str | None = None,
        cloud_pass: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._app_token = app_token
        self._cloud_url = cloud_url
        self._cloud_user = cloud_user
        self._cloud_pass = cloud_pass
        self._session_token: str | None = None
        self._csrf_token: str | None = None
        self._digest_params: dict = {}
        self._session = session
        self._own_session = session is None
        self._ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self._ssl_context.check_hostname = False
        self._ssl_context.verify_mode = ssl.CERT_NONE

    @property
    def is_cloud(self) -> bool:
        return self._cloud_url is not None

    @property
    def base_url(self) -> str:
        if self.is_cloud:
            return self._cloud_url.rstrip("/")
        return f"https://{self._host}:{self._port}"

    async def _ensure_session(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._own_session = True

    async def close(self) -> None:
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    def _get_digest_uri(self, url: str, params: dict) -> str:
        """Build the URI for Digest auth (path + query string)."""
        parsed = URL(url)
        if params:
            parsed = parsed.with_query(params)
        uri = str(parsed.path)
        if parsed.query_string:
            uri += "?" + str(parsed.query_string)
        return uri

    async def _cloud_get(
        self, url: str, params: dict | None = None, timeout_val: int = 15,
    ) -> tuple[int, Any]:
        """Execute GET with HTTP Digest auth + CSRF for cloud."""
        if params is None:
            params = {}

        uri = self._get_digest_uri(url, params)

        headers = {}
        if self._csrf_token:
            headers["X-CSRF-Token"] = self._csrf_token
            headers["X-Requested-With"] = "XMLHttpRequest"

        if self._digest_params:
            headers["Authorization"] = _build_digest_header(
                self._cloud_user, self._cloud_pass, "GET", uri,
                self._digest_params.get("realm", ""),
                self._digest_params.get("nonce", ""),
                self._digest_params.get("qop", ""),
            )

        async with self._session.get(
            url, params=params, headers=headers,
            ssl=self._ssl_context,
            timeout=aiohttp.ClientTimeout(total=timeout_val),
        ) as resp:
            if resp.status == 401:
                www_auth = resp.headers.get("WWW-Authenticate", "")
                self._digest_params = _parse_www_authenticate(www_auth)

                headers["Authorization"] = _build_digest_header(
                    self._cloud_user, self._cloud_pass, "GET", uri,
                    self._digest_params.get("realm", ""),
                    self._digest_params.get("nonce", ""),
                    self._digest_params.get("qop", ""),
                )

                async with self._session.get(
                    url, params=params, headers=headers,
                    ssl=self._ssl_context,
                    timeout=aiohttp.ClientTimeout(total=timeout_val),
                ) as resp2:
                    for cookie in self._session.cookie_jar:
                        if cookie.key == "csrf-token":
                            self._csrf_token = cookie.value
                    if resp2.status == 200:
                        return 200, await resp2.json(content_type=None)
                    return resp2.status, None

            for cookie in self._session.cookie_jar:
                if cookie.key == "csrf-token":
                    self._csrf_token = cookie.value

            if resp.status == 200:
                return 200, await resp.json(content_type=None)
            return resp.status, None

    async def _request(self, endpoint: str, params: dict | None = None) -> dict:
        """Execute API request and return result dict."""
        await self._ensure_session()
        url = f"{self.base_url}{endpoint}"
        if params is None:
            params = {}

        try:
            if self.is_cloud:
                status, data = await self._cloud_get(url, params)
                if status == 401:
                    raise DigitalStromAuthError("Authentication failed (401)")
                if status == 403:
                    raise DigitalStromAuthError("Forbidden (403)")
                if status != 200 or data is None:
                    raise DigitalStromApiError(f"HTTP {status}")
            else:
                if self._session_token:
                    params["token"] = self._session_token
                async with self._session.get(
                    url, params=params,
                    ssl=self._ssl_context,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 401:
                        raise DigitalStromAuthError("Authentication failed (401)")
                    if resp.status == 403:
                        raise DigitalStromAuthError("Forbidden (403)")
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)

            if not data.get("ok", False):
                msg = data.get("message", "Unknown API error")
                if "not logged in" in msg.lower() or "token" in msg.lower():
                    raise DigitalStromAuthError(msg)
                raise DigitalStromApiError(msg)

            return data.get("result", data)

        except aiohttp.ClientError as err:
            raise DigitalStromApiError(f"Connection error: {err}") from err

    # =====================================================================
    # Authentication
    # =====================================================================

    async def connect(self) -> bool:
        """Establish connection and authenticate."""
        if self.is_cloud:
            return await self._connect_cloud()
        return await self._connect_local()

    async def _connect_local(self) -> bool:
        if not self._app_token:
            raise DigitalStromAuthError("No application token configured")
        result = await self._request(
            "/json/system/loginApplication",
            {"loginToken": self._app_token},
        )
        self._session_token = result.get("token")
        if not self._session_token:
            raise DigitalStromAuthError("No session token received")
        _LOGGER.info("Connected to dSS (local) at %s", self.base_url)
        return True

    async def _connect_cloud(self) -> bool:
        await self._ensure_session()
        status, _ = await self._cloud_get(self.base_url, {})
        if status != 200:
            raise DigitalStromAuthError(f"Cloud auth failed (HTTP {status})")
        await self.get_version()
        _LOGGER.info("Connected to dSS (cloud) at %s", self.base_url)
        return True

    async def request_app_token(self, app_name: str = DSS_APP_NAME) -> str:
        """Request application token. User must approve in dSS admin."""
        result = await self._request(
            "/json/system/requestApplicationToken",
            {"applicationName": app_name},
        )
        return result.get("applicationToken", "")

    async def check_app_token(self, token: str) -> bool:
        """Try to login with a pending token. Returns True if approved."""
        try:
            result = await self._request(
                "/json/system/loginApplication",
                {"loginToken": token},
            )
            if result.get("token"):
                self._app_token = token
                self._session_token = result["token"]
                return True
        except DigitalStromApiError:
            pass
        return False

    # =====================================================================
    # System queries
    # =====================================================================

    async def get_version(self) -> dict:
        return await self._request("/json/system/version")

    async def get_time(self) -> dict:
        """Get dSS server time."""
        return await self._request("/json/system/time")

    # =====================================================================
    # Apartment / Structure queries
    # =====================================================================

    async def get_structure(self) -> dict:
        return await self._request("/json/apartment/getStructure")

    async def get_consumption(self) -> int:
        """Get total apartment power consumption in Watts."""
        result = await self._request("/json/apartment/getConsumption")
        return result.get("consumption", 0)

    async def get_temperature_values(self) -> list[dict]:
        """Get temperature control values per zone."""
        result = await self._request("/json/apartment/getTemperatureControlValues")
        return result.get("zones", [])

    async def get_sensor_values(self) -> dict:
        """Get all sensor values: weather, outdoor, and per-zone.

        Returns dict with keys: weather, outdoor, zones
        PRO FEATURE.
        """
        return await self._request("/json/apartment/getSensorValues")

    async def get_zone_sensor_values(self, zone_id: int) -> dict:
        """Get sensor values for a specific zone.

        Returns pre-scaled values (TemperatureValue, HumidityValue,
        CO2concentrationValue, BrightnessValue, etc.).
        FREE — no license required.
        """
        return await self._request(
            "/json/zone/getSensorValues",
            {"id": zone_id},
        )

    async def get_circuits(self) -> list[dict]:
        """Get list of dSM circuits (energy meters).

        PRO FEATURE.
        """
        result = await self._request("/json/apartment/getCircuits")
        return result.get("circuits", [])

    async def get_reachable_groups(self, zone_id: int) -> list[dict]:
        """Get groups with active devices in a zone."""
        result = await self._request(
            "/json/apartment/getReachableGroups",
            {"id": zone_id},
        )
        return result.get("groups", [])

    # =====================================================================
    # Zone commands (scenes, values, dimming)
    # =====================================================================

    async def call_scene(self, zone_id: int, group: int, scene_number: int) -> None:
        await self._request(
            "/json/zone/callScene",
            {"id": zone_id, "groupID": group, "sceneNumber": scene_number},
        )

    async def undo_scene(self, zone_id: int, group: int, scene_number: int) -> None:
        await self._request(
            "/json/zone/undoScene",
            {"id": zone_id, "groupID": group, "sceneNumber": scene_number},
        )

    async def turn_on(self, zone_id: int, group: int = 1) -> None:
        await self._request(
            "/json/zone/turnOn",
            {"id": zone_id, "groupID": group},
        )

    async def turn_off(self, zone_id: int, group: int = 1) -> None:
        await self._request(
            "/json/zone/turnOff",
            {"id": zone_id, "groupID": group},
        )

    async def set_value(self, zone_id: int, group: int, value: int) -> None:
        """Set output value (0-255) for zone/group."""
        await self._request(
            "/json/zone/setValue",
            {"id": zone_id, "groupID": group, "value": max(0, min(255, value))},
        )

    async def increase_value(self, zone_id: int, group: int) -> None:
        """Increase output value by one step (smooth dimming).

        PRO FEATURE.
        """
        await self._request(
            "/json/zone/increaseValue",
            {"id": zone_id, "groupID": group},
        )

    async def decrease_value(self, zone_id: int, group: int) -> None:
        """Decrease output value by one step (smooth dimming).

        PRO FEATURE.
        """
        await self._request(
            "/json/zone/decreaseValue",
            {"id": zone_id, "groupID": group},
        )

    # =====================================================================
    # Zone scene discovery & naming
    # =====================================================================

    async def get_reachable_scenes(self, zone_id: int, group: int) -> dict:
        """Get reachable scenes and their user-defined names.

        Returns: {"reachableScenes": [0, 5, 17, ...], "userSceneNames": [{"sceneNr": 5, "sceneName": "Dag"}, ...]}
        """
        return await self._request(
            "/json/zone/getReachableScenes",
            {"id": zone_id, "groupID": group},
        )

    async def get_last_called_scene(self, zone_id: int, group: int) -> int:
        """Get the last called scene number for a zone/group.

        Returns scene number (int).
        """
        result = await self._request(
            "/json/zone/getLastCalledScene",
            {"id": zone_id, "groupID": group},
        )
        return result.get("scene", -1)

    async def get_scene_name(self, zone_id: int, group: int, scene_number: int) -> str:
        """Get user-defined scene name. Returns empty string if not set."""
        try:
            result = await self._request(
                "/json/zone/sceneGetName",
                {"id": zone_id, "groupID": group, "sceneNumber": scene_number},
            )
            return result.get("name", "")
        except DigitalStromApiError:
            return ""

    async def save_scene(self, zone_id: int, group: int, scene_number: int) -> None:
        """Save current output values as a scene.

        PRO FEATURE.
        """
        await self._request(
            "/json/zone/saveScene",
            {"id": zone_id, "groupID": group, "sceneNumber": scene_number},
        )

    # =====================================================================
    # Zone climate control
    # =====================================================================

    async def get_temperature_control_status(self, zone_id: int) -> dict:
        """Get climate control status for a zone.

        Returns: ControlMode, OperationMode, TemperatureValue, NominalValue, ControlValue
        PRO FEATURE.
        """
        return await self._request(
            "/json/zone/getTemperatureControlStatus",
            {"id": zone_id},
        )

    async def get_temperature_control_config(self, zone_id: int) -> dict:
        """Get climate control configuration for a zone.

        Returns: mode, targetTemperatures (per scene), controlMode params
        PRO FEATURE.
        """
        return await self._request(
            "/json/zone/getTemperatureControlConfig2",
            {"id": zone_id},
        )

    async def set_temperature_control_values(
        self, zone_id: int, nominal_value: float
    ) -> None:
        """Set target temperature for a zone.

        PRO FEATURE.
        """
        await self._request(
            "/json/zone/setTemperatureControlValues",
            {"id": zone_id, "NominalValue": nominal_value},
        )

    # =====================================================================
    # Device queries
    # =====================================================================

    async def get_device_state(self, dsuid: str) -> bool:
        """Get device on/off state. Returns True if on."""
        result = await self._request(
            "/json/device/getState",
            {"dsuid": dsuid},
        )
        return result.get("isOn", False)

    async def get_all_binary_input_states(self) -> dict[str, int]:
        """Get binary input states for ALL devices via apartment/getDevices.

        Returns dict of {dsuid: state} where state is 1 (active) or 2 (inactive).
        This is the only reliable API for binary input states — getState returns
        isOn which reflects output state (always True for outputMode=0 devices),
        and property tree paths don't exist for binary inputs.
        """
        result = await self._request("/json/apartment/getDevices")
        states = {}

        # Debug: log the type and structure of the API response
        if isinstance(result, dict):
            _LOGGER.debug(
                "getDevices returned dict with keys: %s",
                list(result.keys())[:10],
            )
            # Some dSS firmware versions wrap devices in a key
            if "devices" in result:
                result = result["devices"]
            elif not isinstance(result, list):
                _LOGGER.warning(
                    "getDevices unexpected format: type=%s, sample=%s",
                    type(result).__name__, str(result)[:200],
                )

        device_count = 0
        bi_count = 0
        for dev in result if isinstance(result, list) else []:
            device_count += 1
            dsuid = dev.get("dSUID", "")
            bi = dev.get("binaryInputs", [])
            if dsuid and bi:
                bi_count += 1
                if "state" in bi[0]:
                    states[dsuid] = bi[0]["state"]
                else:
                    _LOGGER.debug(
                        "Device %s has binaryInputs but no 'state' key: %s",
                        dsuid[:12], bi[0],
                    )
        _LOGGER.debug(
            "getDevices: %d devices total, %d with binaryInputs, %d with state",
            device_count, bi_count, len(states),
        )
        return states

    async def get_device_output_value(self, dsuid: str, offset: int = 0) -> int:
        """Get device output value at given offset."""
        result = await self._request(
            "/json/device/getOutputValue",
            {"dsuid": dsuid, "offset": offset},
        )
        return result.get("value", 0)

    async def get_device_sensor_value(self, dsuid: str, sensor_index: int = 0) -> dict:
        """Get device sensor value. Returns {sensorIndex, value, age, timestamp}."""
        return await self._request(
            "/json/device/getSensorValue2",
            {"dsuid": dsuid, "sensorIndex": sensor_index},
        )

    async def device_turn_on(self, dsuid: str) -> None:
        """Turn on a single device by dSUID."""
        await self._request(
            "/json/device/turnOn",
            {"dsuid": dsuid},
        )

    async def device_turn_off(self, dsuid: str) -> None:
        """Turn off a single device by dSUID."""
        await self._request(
            "/json/device/turnOff",
            {"dsuid": dsuid},
        )

    async def blink_device(self, dsuid: str) -> None:
        """Make a device blink for identification.

        PRO FEATURE.
        """
        await self._request(
            "/json/device/blink",
            {"dsuid": dsuid},
        )

    # =====================================================================
    # Metering (energy history)
    # =====================================================================

    async def get_metering_latest(
        self, meter_dsuid: str = ".meters(all)", meter_type: str = "consumption"
    ) -> list[dict]:
        """Get latest metering values.

        meter_type: "consumption" (W), "energy" (Wh)
        PRO FEATURE.
        """
        result = await self._request(
            "/json/metering/getLatest",
            {"from": meter_dsuid, "type": meter_type},
        )
        return result.get("values", [])

    async def get_metering_values(
        self,
        meter_dsuid: str,
        meter_type: str = "consumption",
        resolution: int = 300,
        value_count: int = 100,
        unit: str = "W",
    ) -> list[dict]:
        """Get historical metering values.

        resolution: seconds (60, 300, 3600)
        PRO FEATURE.
        """
        result = await self._request(
            "/json/metering/getValues",
            {
                "from": meter_dsuid,
                "type": meter_type,
                "resolution": resolution,
                "valueCount": value_count,
                "unit": unit,
            },
        )
        return result.get("values", [])

    async def get_circuit_energy(self, dsuid: str) -> int:
        """Get cumulative energy meter value for a circuit (Watt-seconds).

        Returned value is the lifetime accumulated energy of the dSM,
        suitable for HA Energy Dashboard (state_class=total_increasing)
        after conversion: kWh = Ws / 3_600_000.
        """
        result = await self._request(
            "/json/circuit/getEnergyMeterValue",
            {"dsuid": dsuid},
        )
        return result.get("meterValue", 0)

    # =====================================================================
    # User Defined Actions & States (apartment-level automation primitives)
    # =====================================================================

    async def get_user_defined_actions(self) -> list[dict]:
        """Fetch User Defined Actions from the dSS property tree.

        Returned actions originate from the dSS "user-defined actions" addon
        (configured in the Configurator). Each item has: id, name, source,
        disabled (bool).
        """
        result = await self._request(
            "/json/property/query2",
            {"query": "/usr/events/*(id,name,source,disabled)"},
        )
        items = []
        for _, entry in result.items():
            if isinstance(entry, dict) and entry.get("id"):
                items.append({
                    "id": str(entry.get("id", "")),
                    "name": entry.get("name", ""),
                    "source": entry.get("source", ""),
                    "disabled": bool(entry.get("disabled", False)),
                })
        return items

    async def get_user_defined_states(self) -> list[dict]:
        """Fetch User Defined / apartment-wide states from /usr/states.

        Each item has: name, state (str), value (int|str). Binary states
        report value 1=active, 2=inactive.
        """
        result = await self._request(
            "/json/property/query2",
            {"query": "/usr/states/*(name,state,value)"},
        )
        items = []
        for key, entry in result.items():
            if not isinstance(entry, dict):
                continue
            items.append({
                "name": entry.get("name", key),
                "state": entry.get("state", ""),
                "value": entry.get("value"),
            })
        return items

    async def get_custom_state_definitions(self) -> list[dict]:
        """Fetch User Defined State definitions from the dSS Configurator addon.

        These are the entries the user creates in the Configurator under
        *Activities > User Defined States* (the custom-states subtree of the
        system-addon-user-defined-states script). Each item has:
            id, name, setName, resetName, showOnPhone
        Their *current value* lives in ``get_addon_states`` below.
        """
        result = await self._request(
            "/json/property/query2",
            {"query": "/scripts/system-addon-user-defined-states/custom-states/*(id,name,setName,resetName,showOnPhone)"},
        )
        items = []
        for _, entry in result.items():
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            items.append({
                "id": str(entry["id"]),
                "name": entry.get("name", ""),
                "set_name": entry.get("setName", "Active"),
                "reset_name": entry.get("resetName", "Inactive"),
                "show_on_phone": bool(entry.get("showOnPhone", False)),
            })
        return items

    async def get_addon_states(self, addon: str = "system-addon-user-defined-states") -> dict[str, dict]:
        """Fetch the runtime state of a script addon from /usr/addon-states.

        Returns ``{name: {"state": str, "value": int|str}}``. For custom user
        defined states the ``name`` equals the state id used to cross-reference
        with :meth:`get_custom_state_definitions`.
        """
        result = await self._request(
            "/json/property/query2",
            {"query": f"/usr/addon-states/{addon}/*(name,state,value)"},
        )
        items: dict[str, dict] = {}
        for key, entry in result.items():
            if not isinstance(entry, dict):
                continue
            name = entry.get("name", key)
            items[name] = {
                "state": entry.get("state", ""),
                "value": entry.get("value"),
            }
        return items

    async def get_state_value(self, name: str) -> dict:
        """Get the current value of a named state. Returns {value: ...}."""
        try:
            return await self._request(
                "/json/state/get",
                {"name": name},
            )
        except DigitalStromApiError:
            return {}

    async def raise_event(self, name: str, parameter: str | None = None) -> None:
        """Raise a system event by name. Used to trigger User Defined Actions."""
        params: dict[str, Any] = {"name": name}
        if parameter:
            params["parameter"] = parameter
        await self._request("/json/event/raise", params)

    # =====================================================================
    # Event subscription
    # =====================================================================

    async def subscribe_events(self) -> int:
        """Subscribe to dSS events. Returns subscription ID."""
        sub_id = EVENT_SUBSCRIPTION_ID
        event_names = [
            "callScene",
            "undoScene",
            "zoneSensorValue",
            "stateChange",
            "deviceSensorValue",
            "running",
        ]
        for name in event_names:
            try:
                await self._request(
                    "/json/event/subscribe",
                    {"subscriptionID": sub_id, "name": name},
                )
            except DigitalStromApiError:
                # Some events may not be available on all firmware versions
                _LOGGER.debug("Could not subscribe to event: %s", name)
        _LOGGER.info("Subscribed to dSS events (ID=%d)", sub_id)
        return sub_id

    async def get_events(
        self, subscription_id: int | None = None, timeout: int = EVENT_POLL_TIMEOUT,
    ) -> list[dict]:
        """Long-poll for events. Returns list of event dicts."""
        sid = subscription_id or EVENT_SUBSCRIPTION_ID
        await self._ensure_session()

        url = f"{self.base_url}/json/event/get"
        params = {"subscriptionID": sid, "timeout": timeout * 1000}

        try:
            if self.is_cloud:
                status, data = await self._cloud_get(url, params, timeout_val=timeout + 10)
                if status == 401:
                    raise DigitalStromAuthError("Session expired")
                if data is None:
                    return []
            else:
                if self._session_token:
                    params["token"] = self._session_token
                async with self._session.get(
                    url, params=params,
                    ssl=self._ssl_context,
                    timeout=aiohttp.ClientTimeout(total=timeout + 10),
                ) as resp:
                    if resp.status == 401:
                        raise DigitalStromAuthError("Session expired")
                    data = await resp.json(content_type=None)

            if not data.get("ok", False):
                msg = data.get("message", "")
                if "not logged in" in msg.lower():
                    raise DigitalStromAuthError(msg)
                return []

            return data.get("result", {}).get("events", [])

        except asyncio.TimeoutError:
            return []
        except aiohttp.ClientError as err:
            raise DigitalStromApiError(f"Event poll error: {err}") from err
