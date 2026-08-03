"""LLM provider abstraction.

`Provider` is the extension point: add new backends (e.g. anthropic) by
subclassing it without touching upper layers.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

from pydantic import BaseModel

from opennovel.llm.types import ChatMessage, CompletionRequest, CompletionResponse

JSON_HINT = "请以 JSON 输出，不要输出任何其他内容。"


class LLMError(RuntimeError):
    """Base error for LLM call failures (network, API error, bad payload)."""


class Provider(ABC):
    """Abstract LLM provider. `model` is the fallback when requests omit one."""

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """One chat completion call. Honors `request.schema` (JSON mode)."""

    def complete_structured(
        self, request: CompletionRequest, schema: type[BaseModel]
    ) -> BaseModel:
        """Call `complete` expecting JSON, parse and validate against `schema`."""
        req = CompletionRequest(
            messages=[ChatMessage(role="system", content=JSON_HINT), *request.messages],
            model=request.model or self.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            schema=schema,
            extra=request.extra,
        )
        response = self.complete(req)
        try:
            return schema.model_validate_json(response.text)
        except Exception as exc:
            raise LLMError(
                f"structured output failed to parse against {schema.__name__}: {response.text[:200]!r}"
            ) from exc


class OpenAICompatibleProvider(Provider):
    """openai SDK pointed at an OpenAI-compatible endpoint via base_url.

    Covers DeepSeek / 通义千问 / 智谱 GLM / Moonshot / OpenAI itself.
    """

    def __init__(self, api_key: str, base_url: str | None, model: str, timeout: float = 60.0):
        super().__init__(model)
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        kwargs: dict = {}
        if request.schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            raw = self._client.chat.completions.create(
                model=request.model or self.model,
                messages=[m.__dict__ for m in request.messages],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                **kwargs,
            )
        except Exception as exc:
            raise LLMError(f"LLM call failed: {exc}") from exc

        text = raw.choices[0].message.content or ""
        usage = raw.usage.model_dump() if raw.usage else None
        return CompletionResponse(text=text, model=raw.model, usage=usage)


class FakeProvider(Provider):
    """Deterministic in-memory provider for tests (no network)."""

    def __init__(self, model: str = "fake", replies: list[str] | None = None):
        super().__init__(model)
        self.replies = list(replies or [])
        self.calls: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.calls.append(request)
        text = self.replies.pop(0) if self.replies else ""
        return CompletionResponse(text=text, model=self.model)

    def enqueue(self, *replies: str) -> None:
        self.replies.extend(replies)

    @staticmethod
    def json_reply(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False)
