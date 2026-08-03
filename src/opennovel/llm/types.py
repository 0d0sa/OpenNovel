"""Internal types for the LLM provider layer.

The agent orchestration only talks to these types (and `Provider`); SDK
specifics never leak past `llm/`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    """One message in a chat conversation."""

    role: Role
    content: str


@dataclass
class CompletionRequest:
    """A completion request.

    `schema` marks the call as structured-output: the provider should return
    JSON matching that Pydantic model (used via `complete_structured`).
    """

    messages: list[ChatMessage]
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048
    schema: type[BaseModel] | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class CompletionResponse:
    """A completion result."""

    text: str
    model: str
    usage: dict | None = None
