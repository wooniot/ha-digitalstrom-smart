"""Pro license validation + repair-issue helpers.

Lives in its own module so both __init__ (setup) and the coordinator
(periodic recheck) can use it without a circular import.
"""

import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, PRO_LICENSE_URL

_LOGGER = logging.getLogger(__name__)

# Repair-issue id shown in Settings > System > Repairs when a Pro key is
# configured but no longer validates (e.g. license unbound after a dSS
# firmware update flipped the dSS id). Non-flapping: created when invalid,
# deleted when valid.
ISSUE_PRO_INVALID = "pro_license_invalid"


async def check_pro_license(key: str, dss_id: str, hass: HomeAssistant | None = None) -> dict:
    """Validate Pro license key with the WoonIoT server.

    Returns dict with: valid, reason, type, method (online/offline).
    """
    if not key:
        return {"valid": False, "reason": "no_key", "type": None, "method": None}
    dss_short = dss_id[:8] if dss_id else ""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                PRO_LICENSE_URL,
                json={"key": key, "dss_id": dss_short},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if hass is not None:
                        await _cache_save(hass, key, bool(data.get("valid", False)), data.get("type"))
                    return {
                        "valid": data.get("valid", False),
                        "reason": data.get("reason", "ok" if data.get("valid") else "unknown"),
                        "type": data.get("type"),
                        "method": "online",
                        "dss_id_sent": dss_short,
                    }
    except Exception:
        pass
    # Offline fallback: the last successful ONLINE result for this key, at most
    # OFFLINE_GRACE_DAYS old. No signing secret in the client (nov 2026): a secret
    # in published code lets anyone forge keys once the server is unreachable.
    cached = await _cache_load(hass, key) if hass is not None else None
    valid = bool(cached and cached.get("valid"))
    return {
        "valid": valid,
        "reason": "ok" if valid else "offline_no_cache",
        "type": cached.get("type") if valid else "offline",
        "method": "offline",
        "dss_id_sent": dss_short,
    }


OFFLINE_GRACE_DAYS = 30
_CACHE_STORE_KEY = f"{DOMAIN}_license_cache"


def _cache_store(hass: HomeAssistant):
    from homeassistant.helpers.storage import Store
    return Store(hass, 1, _CACHE_STORE_KEY)


async def _cache_save(hass: HomeAssistant, key: str, valid: bool, ltype) -> None:
    import time
    try:
        await _cache_store(hass).async_save(
            {"key": key, "valid": valid, "type": ltype, "checked_at": time.time()})
    except Exception as err:  # cache is best effort
        _LOGGER.debug("License cache save failed: %s", err)


async def _cache_load(hass: HomeAssistant, key: str):
    import time
    try:
        data = await _cache_store(hass).async_load()
    except Exception:
        return None
    if not data or data.get("key") != key or not data.get("valid"):
        return None
    if time.time() - float(data.get("checked_at") or 0) > OFFLINE_GRACE_DAYS * 86400:
        return None
    return data


@callback
def sync_pro_issue(hass: HomeAssistant, entry_id: str, has_key: bool, valid: bool) -> None:
    """Create or clear the 'Pro license inactive' repair issue.

    Only raised when a key IS configured but does not validate — so a user
    whose Pro features silently disappeared (e.g. after a firmware update)
    gets a clear, actionable notification instead of a quiet drop to Free.
    """
    issue_id = f"{ISSUE_PRO_INVALID}_{entry_id}"
    if has_key and not valid:
        ir.async_create_issue(
            hass, DOMAIN, issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_PRO_INVALID,
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
