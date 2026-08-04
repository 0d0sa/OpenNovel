"""Provider factory: build a Provider from environment configuration."""

from __future__ import annotations

from typing import Mapping

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


def provider_from_env(env: Mapping[str, str] | None = None) -> Provider:
    """Build a provider from env vars (via `Settings`).

    - OPENNOVEL_LLM_API_KEY: required (falls back to OPENAI_API_KEY)
    - OPENNOVEL_LLM_MODEL: required
    - OPENNOVEL_LLM_BASE_URL: optional; omit to use OpenAI's official endpoint
    - OPENNOVEL_LLM_TEMPERATURE / OPENNOVEL_LLM_MAX_TOKENS: defaults used for
      every request unless overridden
    """
    settings = load_settings(env)
    if not settings.llm_api_key:
        raise ProviderConfigError(
            "missing API key: set OPENNOVEL_LLM_API_KEY (or OPENAI_API_KEY)"
        )
    if not settings.llm_model:
        raise ProviderConfigError("missing model: set OPENNOVEL_LLM_MODEL")
    return OpenAICompatibleProvider(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        call_interval=settings.llm_call_interval,
    )
