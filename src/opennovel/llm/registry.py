"""Provider factory: build a Provider from environment configuration."""

from __future__ import annotations

import os
from typing import Mapping

from opennovel.llm.provider import OpenAICompatibleProvider, Provider

ENV_API_KEY = "OPENNOVEL_LLM_API_KEY"
ENV_BASE_URL = "OPENNOVEL_LLM_BASE_URL"
ENV_MODEL = "OPENNOVEL_LLM_MODEL"


class ProviderConfigError(RuntimeError):
    """Missing/invalid configuration for building a provider."""


def provider_from_env(env: Mapping[str, str] | None = None) -> Provider:
    """Build a provider from env vars.

    - OPENNOVEL_LLM_API_KEY: required (falls back to OPENAI_API_KEY)
    - OPENNOVEL_LLM_BASE_URL: optional; omit to use OpenAI's official endpoint
    - OPENNOVEL_LLM_MODEL: required, e.g. deepseek-chat
    """
    env = os.environ if env is None else env
    api_key = env.get(ENV_API_KEY) or env.get("OPENAI_API_KEY")
    if not api_key:
        raise ProviderConfigError(
            f"missing API key: set {ENV_API_KEY} (or OPENAI_API_KEY)"
        )
    model = env.get(ENV_MODEL)
    if not model:
        raise ProviderConfigError(f"missing model: set {ENV_MODEL}")
    base_url = env.get(ENV_BASE_URL) or None
    return OpenAICompatibleProvider(api_key=api_key, base_url=base_url, model=model)
