"""User-level settings store managed exclusively by ``/setting``.

Stored at ``~/.config/opennovel/settings.json``: named LLM profiles plus
global generation/runtime settings. Written atomically with 0600 permissions
because the file contains API keys.
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


class RuntimeConfig(BaseModel):
    """Global generation/runtime settings shared by all model profiles."""

    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="采样温度")
    max_tokens: int = Field(default=4096, gt=0, description="单次调用 token 上限")
    call_interval: float = Field(default=0.0, ge=0.0, description="调用间隔秒数")
    language: str = Field(default="zh", min_length=1, description="成书语言")
    chapter_target_chars: int = Field(default=3000, gt=0, description="每章目标字数")
    max_chapters: int = Field(default=20, gt=0, description="最大章节数")
    output_dir: str = Field(default="novels", min_length=1, description="成书输出目录")
    style_check: bool = Field(default=True, description="风格一致性检查")
    plot_check: bool = Field(default=True, description="剧情一致性检查")


class UserSettings(BaseModel):
    """Persisted settings: named profiles, active profile, and runtime knobs."""

    active: str = ""
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    def active_profile(self) -> ProfileConfig | None:
        return self.profiles.get(self.active)


def default_config_path() -> Path:
    """Return the single location used by the ``/setting`` command."""
    return Path.home() / ".config" / "opennovel" / "settings.json"


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
