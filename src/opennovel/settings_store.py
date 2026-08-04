"""User-level settings store for named LLM profiles.

Stored at `~/.config/opennovel/settings.json` (override via
OPENNOVEL_CONFIG_FILE): multiple named profiles (base_url / api_key / model)
with an active one. Written atomically with 0600 permissions — the file
contains secrets.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field


class ProfileConfig(BaseModel):
    """One named LLM configuration."""

    name: str = Field(description="配置名")
    base_url: str | None = Field(default=None, description="服务地址；None = OpenAI 官方")
    api_key: str = Field(description="API 密钥")
    model: str = Field(description="模型名")


class UserSettings(BaseModel):
    """Persisted user settings: named profiles + the active one."""

    active: str = ""
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)

    def active_profile(self) -> ProfileConfig | None:
        return self.profiles.get(self.active)


def default_config_path() -> Path:
    override = os.environ.get("OPENNOVEL_CONFIG_FILE")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "opennovel" / "settings.json"


def load_user_settings(path: Path | None = None) -> UserSettings | None:
    """Load settings; returns None when the file does not exist."""
    path = Path(path) if path else default_config_path()
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return UserSettings.model_validate(data)


def save_user_settings(settings: UserSettings, path: Path | None = None) -> Path:
    """Write settings atomically (tmp file + rename) with 0600 permissions."""
    path = Path(path) if path else default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = settings.model_dump_json(indent=2)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def mask_key(api_key: str) -> str:
    """Mask a key for display: `sk-****1234`."""
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:3]}****{api_key[-4:]}"
