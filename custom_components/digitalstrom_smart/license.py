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


async def check_pro_license(key: str, dss_id: str) -> dict:
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
