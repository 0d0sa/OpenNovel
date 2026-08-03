"""Tests for the LLM provider layer."""

import os

import pytest
from pydantic import BaseModel, Field

from opennovel.llm import (
    ChatMessage,
    CompletionRequest,
    FakeProvider,
    LLMError,
    OpenAICompatibleProvider,
    ProviderConfigError,
    provider_from_env,
)


class Outline(BaseModel):
    title: str = Field(description="章节标题")
    summary: str = Field(description="大纲")


def test_chat_message_and_request_construction():
    msg = ChatMessage(role="user", content="写一段")
    req = CompletionRequest(messages=[msg], model="deepseek-chat", max_tokens=512)
    assert req.messages[0].content == "写一段"
    assert req.temperature is None  # falls back to provider defaults
    assert req.schema is None


def test_provider_defaults_fill_request_knobs():
    provider = FakeProvider(model="fake", temperature=0.9, max_tokens=2048)
    provider.enqueue("x")
    provider.complete(CompletionRequest(messages=[ChatMessage(role="user", content="hi")]))
    sent = provider.calls[0]
    assert sent.temperature == 0.9
    assert sent.max_tokens == 2048


def test_request_knobs_override_provider_defaults():
    provider = FakeProvider(model="fake", temperature=0.9, max_tokens=2048)
    provider.enqueue("x")
    provider.complete(
        CompletionRequest(
            messages=[ChatMessage(role="user", content="hi")],
            temperature=0.1,
            max_tokens=100,
        )
    )
    sent = provider.calls[0]
    assert sent.temperature == 0.1
    assert sent.max_tokens == 100


def test_provider_from_env_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENNOVEL_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENNOVEL_LLM_MODEL", "deepseek-chat")
    with pytest.raises(ProviderConfigError, match="API key"):
        provider_from_env()


def test_provider_from_env_missing_model_raises(monkeypatch):
    monkeypatch.setenv("OPENNOVEL_LLM_API_KEY", "sk-test")
    monkeypatch.delenv("OPENNOVEL_LLM_MODEL", raising=False)
    with pytest.raises(ProviderConfigError, match="model"):
        provider_from_env()


def test_provider_from_env_builds_openai_compatible(monkeypatch):
    monkeypatch.setenv("OPENNOVEL_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("OPENNOVEL_LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("OPENNOVEL_LLM_MODEL", "deepseek-chat")
    provider = provider_from_env()
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "deepseek-chat"


def test_structured_output_parses_and_validates():
    provider = FakeProvider(model="fake")
    provider.enqueue(provider.json_reply({"title": "第一章", "summary": "抵达雾城"}))
    req = CompletionRequest(messages=[ChatMessage(role="user", content="规划")])

    outline = provider.complete_structured(req, Outline)

    assert isinstance(outline, Outline)
    assert outline.title == "第一章"
    # JSON hint message must be prepended so json_object mode works
    assert provider.calls[0].messages[0].role == "system"
    assert provider.calls[0].schema is Outline


def test_structured_output_invalid_json_raises_llm_error():
    provider = FakeProvider(model="fake")
    provider.enqueue("not json at all")
    req = CompletionRequest(messages=[ChatMessage(role="user", content="规划")])

    with pytest.raises(LLMError, match="structured output failed"):
        provider.complete_structured(req, Outline)


def test_structured_output_missing_fields_raises_llm_error():
    provider = FakeProvider(model="fake")
    provider.enqueue(provider.json_reply({"title": "第一章"}))
    req = CompletionRequest(messages=[ChatMessage(role="user", content="规划")])

    with pytest.raises(LLMError):
        provider.complete_structured(req, Outline)


@pytest.mark.skipif(
    not (os.environ.get("OPENNOVEL_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="requires real API key",
)
def test_real_completion_smoke(monkeypatch):
    monkeypatch.setenv("OPENNOVEL_LLM_MODEL", os.environ.get("OPENNOVEL_LLM_MODEL", "deepseek-chat"))
    provider = provider_from_env()
    response = provider.complete(
        CompletionRequest(messages=[ChatMessage(role="user", content="回复 OK")], max_tokens=16)
    )
    assert response.text
    assert response.model
