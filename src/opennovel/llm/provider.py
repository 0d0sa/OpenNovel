"""LLM provider abstraction.

`Provider` is the extension point: add new backends (e.g. anthropic) by
subclassing it without touching upper layers.
"""

from __future__ import annotations

import dataclasses
import json
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator

from openai import RateLimitError
from pydantic import BaseModel

from opennovel.llm.types import ChatMessage, CompletionRequest, CompletionResponse

JSON_HINT = "请以 JSON 输出，不要输出任何其他内容。"

MAX_ATTEMPTS = 5


class LLMError(RuntimeError):
    """Base error for LLM call failures (network, API error, bad payload)."""


class Provider(ABC):
    """Abstract LLM provider. `model`/`temperature`/`max_tokens` are the
    fallback values used when a request does not override them."""

    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """One chat completion call. Honors `request.schema` (JSON mode)."""

    def stream_complete(self, request: CompletionRequest) -> Iterator[str]:
        """Stream a completion token by token (yields text deltas).

        Default implementation: fall back to a single complete() call and
        yield the whole text at once (used by FakeProvider and simple backends).
        """
        yield self.complete(request).text

    def complete_structured(
        self, request: CompletionRequest, schema: type[BaseModel]
    ) -> BaseModel:
        """Call `complete` expecting JSON, parse and validate against `schema`.

        The schema is injected into the system prompt: `json_object` mode only
        guarantees valid JSON, not JSON that matches our schema.
        """
        schema_json = json.dumps(
            schema.model_json_schema(), ensure_ascii=False, indent=2
        )
        hint = (
            f"{JSON_HINT}\n"
            "必须符合以下 JSON Schema 的字段结构（可省略 description）：\n"
            f"{schema_json}"
        )
        req = CompletionRequest(
            messages=[ChatMessage(role="system", content=hint), *request.messages],
            model=request.model or self.model,
            temperature=request.temperature if request.temperature is not None else self.temperature,
            max_tokens=request.max_tokens if request.max_tokens is not None else self.max_tokens,
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

    def __init__(
        self,
        api_key: str,
        base_url: str | None,
        model: str,
        timeout: float = 60.0,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        call_interval: float = 0.0,
    ):
        super().__init__(model, temperature=temperature, max_tokens=max_tokens)
        self.call_interval = call_interval
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        if self.call_interval > 0:
            time.sleep(self.call_interval)
        kwargs: dict = {}
        if request.schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
        last_exc: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                raw = self._client.chat.completions.create(
                    model=request.model or self.model,
                    messages=[m.__dict__ for m in request.messages],
                    temperature=request.temperature if request.temperature is not None else self.temperature,
                    max_tokens=request.max_tokens if request.max_tokens is not None else self.max_tokens,
                    **kwargs,
                )
                break
            except RateLimitError as exc:
                last_exc = exc
                if attempt == MAX_ATTEMPTS - 1:
                    break
                time.sleep(min(2**attempt * 2.0, 30.0))
            except Exception as exc:
                raise LLMError(f"LLM call failed: {exc}") from exc
        if last_exc is not None:
            raise LLMError(f"LLM call rate-limited after {MAX_ATTEMPTS} attempts: {last_exc}") from last_exc

        text = raw.choices[0].message.content or ""
        usage = raw.usage.model_dump() if raw.usage else None
        return CompletionResponse(text=text, model=raw.model, usage=usage)

    def stream_complete(self, request: CompletionRequest) -> Iterator[str]:
        if self.call_interval > 0:
            time.sleep(self.call_interval)
        kwargs: dict = {}
        if request.schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            stream = self._client.chat.completions.create(
                model=request.model or self.model,
                messages=[m.__dict__ for m in request.messages],
                temperature=request.temperature if request.temperature is not None else self.temperature,
                max_tokens=request.max_tokens if request.max_tokens is not None else self.max_tokens,
                stream=True,
                **kwargs,
            )
        except Exception as exc:
            raise LLMError(f"LLM call failed: {exc}") from exc
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


class FakeProvider(Provider):
    """Deterministic in-memory provider for tests (no network)."""

    def __init__(
        self,
        model: str = "fake",
        replies: list[str] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        super().__init__(model, temperature=temperature, max_tokens=max_tokens)
        self.replies = list(replies or [])
        self.calls: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        request = dataclasses.replace(
            request,
            temperature=request.temperature if request.temperature is not None else self.temperature,
            max_tokens=request.max_tokens if request.max_tokens is not None else self.max_tokens,
        )
        self.calls.append(request)
        text = self.replies.pop(0) if self.replies else ""
        return CompletionResponse(text=text, model=self.model)

    def enqueue(self, *replies: str) -> None:
        self.replies.extend(replies)

    @staticmethod
    def json_reply(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False)
