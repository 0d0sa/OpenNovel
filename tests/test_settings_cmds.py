"""Tests for /setting and /model commands and the settings store."""

import json
import os
import stat
from pathlib import Path

import pytest
from pydantic import ValidationError

from opennovel.config import load_settings
from opennovel.settings_store import (
    default_config_path,
    ProfileConfig,
    RuntimeConfig,
    UserSettings,
    load_user_settings,
    mask_key,
    save_user_settings,
)
from opennovel.ui.repl import handle_command


def make_user_settings() -> UserSettings:
    return UserSettings(
        active="deepseek",
        profiles={
            "deepseek": ProfileConfig(
                name="deepseek",
                base_url="https://api.deepseek.com/v1",
                api_key="sk-deepseek123456",
                model="deepseek-chat",
            ),
            "qwen": ProfileConfig(
                name="qwen",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                api_key="sk-qwen12345678",
                model="qwen-plus",
            ),
        },
    )


def test_store_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    save_user_settings(make_user_settings(), path)
    loaded = load_user_settings(path)
    assert loaded == make_user_settings()
    assert loaded.active_profile().model == "deepseek-chat"


def test_default_config_path_does_not_use_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("OPENNOVEL_CONFIG_FILE", "/tmp/ignored.json")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/also-ignored")

    assert default_config_path() == tmp_path / ".config" / "opennovel" / "settings.json"


def test_store_atomic_no_tmp_leftover(tmp_path):
    path = tmp_path / "settings.json"
    save_user_settings(make_user_settings(), path)
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_store_permissions_0600(tmp_path):
    path = save_user_settings(make_user_settings(), tmp_path / "settings.json")
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600


def test_store_parses_corrupt_file_raises(tmp_path):
    bad = tmp_path / "settings.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(Exception):
        load_user_settings(bad)


def test_mask_key():
    assert mask_key("sk-deepseek123456") == "sk-****3456"
    assert mask_key("short") == "****"


def test_profile_requires_key_and_model():
    with pytest.raises(ValidationError):
        ProfileConfig(name="x")
    with pytest.raises(ValidationError):
        ProfileConfig(name="x", api_key="k")


def test_load_settings_reads_config_file(tmp_path):
    path = tmp_path / "settings.json"
    save_user_settings(make_user_settings(), path)
    s = load_settings(path)
    assert s.llm_api_key == "sk-deepseek123456"
    assert s.llm_model == "deepseek-chat"
    assert s.llm_base_url == "https://api.deepseek.com/v1"


def test_load_settings_ignores_environment_when_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENNOVEL_LLM_API_KEY", "sk-env-key")
    monkeypatch.setenv("OPENNOVEL_LLM_MODEL", "env-model")
    s = load_settings(tmp_path / "nope.json")
    assert s.llm_api_key == ""
    assert s.llm_model == ""
    assert s.llm_base_url is None


def test_setting_flags_saves_and_switches(monkeypatch, tmp_path, make_session):
    from opennovel.llm import FakeProvider
    from opennovel.ui import display

    built = {}

    def fake_builder(profile, settings):
        built["profile"] = profile
        return FakeProvider(model=profile.model)

    monkeypatch.setattr("opennovel.llm.build_provider_from_profile", fake_builder)
    session = make_session()
    handle_command(
        session,
        "/setting --name deepseek --base-url https://api.deepseek.com/v1 --api-key sk-abc12345678 --model deepseek-chat",
    )
    assert built["profile"].model == "deepseek-chat"
    assert session.provider.model == "deepseek-chat"
    us = load_user_settings(tmp_path / "settings.json")
    assert us.active == "deepseek"
    assert "已保存并切换" in session.console.file.getvalue()


def test_setting_wizard_flow(tmp_path, make_session):
    session = make_session()
    lines = iter(
        [
            "deepseek",
            "https://api.deepseek.com/v1",
            "sk-abc12345678",
            "deepseek-chat",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ]
    )
    session.console.input = lambda prompt="", **kwargs: next(lines)
    handle_command(session, "/setting")
    us = load_user_settings(tmp_path / "settings.json")
    assert us.active == "deepseek"
    assert us.profiles["deepseek"].model == "deepseek-chat"
    assert us.runtime.output_dir == str(tmp_path)
    assert us.runtime.max_chapters == 1
    assert us.runtime.chapter_target_chars == 200


def test_setting_runtime_flags_save_and_apply(tmp_path, make_session):
    session = make_session()
    handle_command(
        session,
        "/setting --temperature 0.4 --max-tokens 7000 --interval 3 "
        "--language en --chapter-target-chars 4500 --max-chapters 12 "
        "--output-dir books --style-check off --plot-check on",
    )

    us = load_user_settings(tmp_path / "settings.json")
    assert us.runtime.temperature == 0.4
    assert us.runtime.max_tokens == 7000
    assert us.runtime.call_interval == 3
    assert us.runtime.language == "en"
    assert us.runtime.chapter_target_chars == 4500
    assert us.runtime.max_chapters == 12
    assert us.runtime.output_dir == "books"
    assert us.runtime.style_check is False
    assert us.runtime.plot_check is True
    assert session.settings.llm_temperature == 0.4
    assert session.settings.output_dir == Path("books")


def test_setting_list_masks_key(make_session, monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    save_user_settings(make_user_settings(), path)
    session = make_session()
    handle_command(session, "/setting --list")
    out = session.console.file.getvalue()
    assert "deepseek-chat" in out
    assert "sk-deepseek123456" not in out
    assert "sk-****3456" in out
    assert "*" in out  # active marker


def test_setting_remove(make_session, monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    save_user_settings(make_user_settings(), path)
    session = make_session()
    handle_command(session, "/setting --remove qwen")
    us = load_user_settings(path)
    assert "qwen" not in us.profiles
    assert us.active == "deepseek"


def test_setting_remove_active_unconfigures_session(make_session, tmp_path):
    from opennovel.llm import UnconfiguredProvider

    path = tmp_path / "settings.json"
    save_user_settings(make_user_settings(), path)
    session = make_session()

    handle_command(session, "/setting --remove deepseek")

    us = load_user_settings(path)
    assert us.active == ""
    assert session.settings.llm_model == ""
    assert isinstance(session.provider, UnconfiguredProvider)


def test_model_switch_by_name(make_session, monkeypatch, tmp_path):
    from opennovel.llm import FakeProvider

    built = {}

    def fake_builder(profile, settings):
        built["profile"] = profile
        return FakeProvider(model=profile.model)

    monkeypatch.setattr("opennovel.llm.build_provider_from_profile", fake_builder)
    path = tmp_path / "settings.json"
    save_user_settings(make_user_settings(), path)
    session = make_session()
    handle_command(session, "/model qwen")
    assert built["profile"].name == "qwen"
    assert session.provider.model == "qwen-plus"
    assert load_user_settings(path).active == "qwen"


def test_model_switch_by_index(make_session, monkeypatch, tmp_path):
    from opennovel.llm import FakeProvider

    built = []

    def fake_builder(profile, settings):
        built.append(profile)
        return FakeProvider(model=profile.model)

    monkeypatch.setattr("opennovel.llm.build_provider_from_profile", fake_builder)
    path = tmp_path / "settings.json"
    save_user_settings(make_user_settings(), path)
    session = make_session()
    handle_command(session, "/model 2")
    assert built[-1].name == "qwen"


def test_model_switch_interactive_prompt(make_session, monkeypatch, tmp_path):
    from opennovel.llm import FakeProvider

    built = []

    def fake_builder(profile, settings):
        built.append(profile)
        return FakeProvider(model=profile.model)

    monkeypatch.setattr("opennovel.llm.build_provider_from_profile", fake_builder)
    path = tmp_path / "settings.json"
    save_user_settings(make_user_settings(), path)
    session = make_session()
    session.console.input = lambda prompt="": "2"
    handle_command(session, "/model")
    assert built and built[-1].name == "qwen"


def test_model_switch_unknown(make_session, monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    save_user_settings(make_user_settings(), path)
    session = make_session()
    handle_command(session, "/model nope")
    assert "未找到配置" in session.console.file.getvalue()


def test_model_with_no_profiles(make_session):
    session = make_session()
    handle_command(session, "/model")
    assert "先 /setting" in session.console.file.getvalue()


def test_fullscreen_header_refresh_on_switch(monkeypatch, tmp_path):
    from opennovel.config import Settings
    from opennovel.llm import FakeProvider
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(FakeProvider(model="deepseek-chat"), Settings(output_dir=tmp_path))
    app.session.provider = FakeProvider(model="qwen-plus")
    app._refresh_header()
    assert app.model == "qwen-plus"
    assert app.session.on_provider_change is not None
