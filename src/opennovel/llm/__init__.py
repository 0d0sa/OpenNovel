"""LLM provider layer.

Abstraction over LLM SDKs; orchestration never touches SDK specifics.
Provider choice is OpenAI-compatible services via base_url (see AGENTS.md).
"""

from opennovel.llm.provider import (
    FakeProvider,
    LLMError,
    OpenAICompatibleProvider,
    Provider,
    UnconfiguredProvider,
)
from opennovel.llm.registry import (
    ProviderConfigError,
    build_provider_from_profile,
    provider_from_env,
)
from opennovel.llm.types import ChatMessage, CompletionRequest, CompletionResponse

__all__ = [
    "ChatMessage",
    "CompletionRequest",
    "CompletionResponse",
    "FakeProvider",
    "LLMError",
    "OpenAICompatibleProvider",
    "Provider",
    "ProviderConfigError",
    "UnconfiguredProvider",
    "build_provider_from_profile",
    "provider_from_env",
]
