"""Provider factory backed by the configuration written by ``/setting``."""

from __future__ import annotations

from pathlib import Path

from opennovel.config import Settings, load_settings
from opennovel.llm.provider import OpenAICompatibleProvider, Provider
from opennovel.settings_store import ProfileConfig


class ProviderConfigError(RuntimeError):
    """Missing/invalid configuration for building a provider."""


def build_provider_from_profile(profile: ProfileConfig, settings: Settings) -> Provider:
    """Build a provider from a named profile, inheriting knobs from settings."""
    return OpenAICompatibleProvider(
        api_key=profile.api_key,
        base_url=profile.base_url,
        model=profile.model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        call_interval=settings.llm_call_interval,
    )


def provider_from_settings(
    settings: Settings | None = None, *, path: Path | None = None
) -> Provider:
    """Build a provider from the active profile configured via ``/setting``."""
    settings = settings or load_settings(path)
    if not settings.llm_api_key:
        raise ProviderConfigError(
            "未配置模型：请在会话中用 /setting 配置 API key（或先创建配置文件）"
        )
    if not settings.llm_model:
        raise ProviderConfigError("未配置模型：请在会话中用 /setting 配置模型名")
    return OpenAICompatibleProvider(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        call_interval=settings.llm_call_interval,
    )
