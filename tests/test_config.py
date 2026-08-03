"""Tests for application settings (config.py)."""

import pytest

from opennovel.config import Settings, load_settings


def test_defaults():
    s = load_settings({})
    assert s.llm_api_key == ""
    assert s.llm_model == ""
    assert s.llm_base_url is None
    assert s.llm_temperature == 0.7
    assert s.llm_max_tokens == 4096
    assert s.language == "zh"
    assert s.chapter_target_chars == 3000
    assert s.max_chapters == 20
    assert str(s.output_dir) == "novels"


def test_reads_env_overrides():
    s = load_settings(
        {
            "OPENNOVEL_LLM_API_KEY": "sk-a",
            "OPENNOVEL_LLM_MODEL": "qwen-plus",
            "OPENNOVEL_LLM_BASE_URL": "https://dashscope.example/v1",
            "OPENNOVEL_LLM_TEMPERATURE": "0.9",
            "OPENNOVEL_LLM_MAX_TOKENS": "8192",
            "OPENNOVEL_LANGUAGE": "zh",
            "OPENNOVEL_CHAPTER_TARGET_CHARS": "5000",
            "OPENNOVEL_MAX_CHAPTERS": "10",
            "OPENNOVEL_OUTPUT_DIR": "books",
        }
    )
    assert s.llm_api_key == "sk-a"
    assert s.llm_model == "qwen-plus"
    assert s.llm_base_url == "https://dashscope.example/v1"
    assert s.llm_temperature == 0.9
    assert s.llm_max_tokens == 8192
    assert s.chapter_target_chars == 5000
    assert s.max_chapters == 10
    assert str(s.output_dir) == "books"


def test_api_key_falls_back_to_openai():
    s = load_settings({"OPENAI_API_KEY": "sk-openai"})
    assert s.llm_api_key == "sk-openai"


def test_invalid_number_raises():
    with pytest.raises(ValueError):
        load_settings({"OPENNOVEL_LLM_TEMPERATURE": "hot"})


def test_provider_uses_settings_knobs(monkeypatch):
    from opennovel.llm import OpenAICompatibleProvider, provider_from_env

    monkeypatch.setenv("OPENNOVEL_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("OPENNOVEL_LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("OPENNOVEL_LLM_TEMPERATURE", "0.3")
    monkeypatch.setenv("OPENNOVEL_LLM_MAX_TOKENS", "6000")
    provider = provider_from_env()
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "deepseek-chat"
    assert provider.temperature == 0.3
    assert provider.max_tokens == 6000
