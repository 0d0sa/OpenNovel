"""Real-API availability flag shared by smoke tests.

True when the user settings file has an active profile with api_key + model
(configured via `/setting`). Model config no longer comes from env vars.
"""

from opennovel.settings_store import load_user_settings

REAL_API_AVAILABLE = False
_stored = load_user_settings()
if _stored is not None:
    profile = _stored.active_profile()
    REAL_API_AVAILABLE = bool(profile and profile.api_key and profile.model)
