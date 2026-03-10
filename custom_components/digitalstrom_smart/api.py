"""Async API client for digitalSTROM Server (dSS).

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
        """Execute GET with HTTP Digest auth + CSRF for cloud. Returns (status, json_data)."""
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
            # Handle 401: parse new challenge and retry
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
                    # Update CSRF from cookies
                    for cookie in self._session.cookie_jar:
                        if cookie.key == "csrf-token":
                            self._csrf_token = cookie.value
                    if resp2.status == 200:
                        return 200, await resp2.json(content_type=None)
                    return resp2.status, None

            # Update CSRF from cookies
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

    # --- Authentication ---

    async def connect(self) -> bool:
        """Establish connection and authenticate."""
        if self.is_cloud:
            return await self._connect_cloud()
        return await self._connect_local()

    async def _connect_local(self) -> bool:
        """Login with application token (local)."""
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
        """Authenticate via cloud (HTTP Digest + CSRF)."""
        await self._ensure_session()

        # Initial GET to base URL: triggers 401 → Digest challenge → 200 + CSRF cookie
        status, _ = await self._cloud_get(self.base_url, {})
        if status != 200:
            raise DigitalStromAuthError(f"Cloud auth failed (HTTP {status})")

        # Verify connection works
        await self.get_version()
        _LOGGER.info("Connected to dSS (cloud) at %s", self.base_url)
        return True

    async def request_app_token(self, app_name: str = DSS_APP_NAME) -> str:
        """Request application token. User must press meter button to approve."""
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

    # --- Data queries ---

    async def get_version(self) -> dict:
        return await self._request("/json/system/version")

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

    # --- Zone commands ---

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

    async def get_scene_name(self, zone_id: int, group: int, scene_number: int) -> str:
        """Get the user-defined scene name from dSS. Returns empty string if not set."""
        try:
            result = await self._request(
                "/json/zone/sceneGetName",
                {"id": zone_id, "groupID": group, "sceneNumber": scene_number},
            )
            return result.get("name", "")
        except DigitalStromApiError:
            return ""

    # --- Event subscription ---

    async def subscribe_events(self) -> int:
        """Subscribe to dSS events. Returns subscription ID."""
        sub_id = EVENT_SUBSCRIPTION_ID
        await self._request(
            "/json/event/subscribe",
            {"subscriptionID": sub_id, "name": "callScene"},
        )
        await self._request(
            "/json/event/subscribe",
            {"subscriptionID": sub_id, "name": "undoScene"},
        )
        await self._request(
            "/json/event/subscribe",
            {"subscriptionID": sub_id, "name": "zoneSensorValue"},
        )
        await self._request(
            "/json/event/subscribe",
            {"subscriptionID": sub_id, "name": "stateChange"},
        )
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
