"""LLM provider layer.

Abstraction over LLM SDKs; orchestration never touches SDK specifics.
Provider choice is OpenAI-compatible services via base_url (see AGENTS.md).
"""

from opennovel.llm.provider import (
    FakeProvider,
    LLMError,
    OpenAICompatibleProvider,
    Provider,
)
from opennovel.llm.registry import (
    ENV_API_KEY,
    ENV_BASE_URL,
    ENV_MODEL,
    ProviderConfigError,
    provider_from_env,
)
from opennovel.llm.types import ChatMessage, CompletionRequest, CompletionResponse

__all__ = [
    "ChatMessage",
    "CompletionRequest",
    "CompletionResponse",
    "ENV_API_KEY",
    "ENV_BASE_URL",
    "ENV_MODEL",
    "FakeProvider",
    "LLMError",
    "OpenAICompatibleProvider",
    "Provider",
    "ProviderConfigError",
    "provider_from_env",
]
