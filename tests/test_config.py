"""Tests for application settings (config.py)."""

import pytest
from pydantic import ValidationError

from opennovel.config import load_settings
from opennovel.settings_store import (
    ProfileConfig,
    RuntimeConfig,
    UserSettings,
    save_user_settings,
)


def test_defaults(tmp_path):
    s = load_settings(tmp_path / "missing.json")
    assert s.llm_api_key == ""
    assert s.llm_model == ""
    assert s.llm_base_url is None
    assert s.llm_temperature == 0.7
    assert s.llm_max_tokens == 4096
    assert s.language == "zh"
    assert s.chapter_target_chars == 3000
    assert s.max_chapters == 20
    assert str(s.output_dir) == "novels"


def test_reads_complete_setting_store(tmp_path):
    path = tmp_path / "settings.json"
    save_user_settings(
        UserSettings(
            active="deepseek",
            profiles={
                "deepseek": ProfileConfig(
                    name="deepseek",
                    base_url="https://api.deepseek.com",
                    api_key="sk-test",
                    model="deepseek-chat",
                )
            },
            runtime=RuntimeConfig(
                temperature=0.3,
                max_tokens=6000,
                call_interval=2.5,
                language="en",
                chapter_target_chars=5000,
                max_chapters=10,
                output_dir="books",
                style_check=False,
                plot_check=True,
            ),
        ),
        path,
    )

    s = load_settings(path)

    assert s.llm_api_key == "sk-test"
    assert s.llm_model == "deepseek-chat"
    assert s.llm_base_url == "https://api.deepseek.com"
    assert s.llm_temperature == 0.3
    assert s.llm_max_tokens == 6000
    assert s.llm_call_interval == 2.5
    assert s.language == "en"
    assert s.chapter_target_chars == 5000
    assert s.max_chapters == 10
    assert str(s.output_dir) == "books"
    assert s.style_check is False
    assert s.plot_check is True


def test_environment_variables_are_ignored(monkeypatch, tmp_path):
    variables = {
        "OPENNOVEL_CONFIG_FILE": str(tmp_path / "elsewhere.json"),
        "OPENNOVEL_LLM_API_KEY": "sk-env",
        "OPENNOVEL_LLM_MODEL": "env-model",
        "OPENNOVEL_LLM_BASE_URL": "https://env.example/v1",
        "OPENNOVEL_LLM_TEMPERATURE": "1.9",
        "OPENNOVEL_LLM_MAX_TOKENS": "9999",
        "OPENNOVEL_LLM_INTERVAL": "12",
        "OPENNOVEL_LANGUAGE": "env-language",
        "OPENNOVEL_CHAPTER_TARGET_CHARS": "999",
        "OPENNOVEL_MAX_CHAPTERS": "99",
        "OPENNOVEL_OUTPUT_DIR": "env-books",
        "OPENNOVEL_STYLE_CHECK": "off",
        "OPENNOVEL_PLOT_CHECK": "off",
        "OPENAI_API_KEY": "sk-openai",
    }
    for name, value in variables.items():
        monkeypatch.setenv(name, value)

    s = load_settings(tmp_path / "missing.json")

    assert s.llm_api_key == ""
    assert s.llm_model == ""
    assert s.llm_temperature == 0.7
    assert s.llm_max_tokens == 4096
    assert s.llm_call_interval == 0
    assert s.language == "zh"
    assert s.chapter_target_chars == 3000
    assert s.max_chapters == 20
    assert str(s.output_dir) == "novels"
    assert s.style_check is True
    assert s.plot_check is True


def test_runtime_settings_validate_ranges():
    with pytest.raises(ValidationError):
        RuntimeConfig(temperature=3)
    with pytest.raises(ValidationError):
        RuntimeConfig(max_tokens=0)


def test_provider_uses_persisted_runtime_settings(tmp_path):
    from opennovel.llm import OpenAICompatibleProvider, provider_from_settings

    path = tmp_path / "settings.json"
    save_user_settings(
        UserSettings(
            active="deepseek",
            profiles={
                "deepseek": ProfileConfig(
                    name="deepseek",
                    base_url="https://api.deepseek.com",
                    api_key="sk-test",
                    model="deepseek-chat",
                )
            },
            runtime=RuntimeConfig(temperature=0.3, max_tokens=6000),
        ),
        path,
    )

    provider = provider_from_settings(path=path)

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "deepseek-chat"
    assert provider.temperature == 0.3
    assert provider.max_tokens == 6000
