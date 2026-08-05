"""Application settings loaded exclusively from the ``/setting`` store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from opennovel.settings_store import RuntimeConfig, UserSettings, load_user_settings

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 4096


@dataclass(frozen=True)
class Settings:
    # LLM
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str | None = None
    llm_temperature: float = DEFAULT_TEMPERATURE
    llm_max_tokens: int = DEFAULT_MAX_TOKENS
    llm_call_interval: float = 0.0  # 每次调用前的固定间隔秒数（低 rpm 配额用）
    # Novel generation (used by the orchestrator)
    language: str = "zh"
    chapter_target_chars: int = 3000
    max_chapters: int = 20
    output_dir: Path = Path("novels")
    style_check: bool = True
    plot_check: bool = True


def settings_from_user_settings(user_settings: UserSettings | None) -> Settings:
    """Convert persisted user settings into immutable application settings."""
    profile = user_settings.active_profile() if user_settings else None
    runtime = user_settings.runtime if user_settings else RuntimeConfig()
    return Settings(
        llm_api_key=profile.api_key if profile else "",
        llm_model=profile.model if profile else "",
        llm_base_url=profile.base_url if profile else None,
        llm_temperature=runtime.temperature,
        llm_max_tokens=runtime.max_tokens,
        llm_call_interval=runtime.call_interval,
        language=runtime.language,
        chapter_target_chars=runtime.chapter_target_chars,
        max_chapters=runtime.max_chapters,
        output_dir=Path(runtime.output_dir),
        style_check=runtime.style_check,
        plot_check=runtime.plot_check,
    )


def runtime_from_settings(settings: Settings) -> RuntimeConfig:
    """Build a persisted runtime model from an in-memory Settings object."""
    return RuntimeConfig(
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        call_interval=settings.llm_call_interval,
        language=settings.language,
        chapter_target_chars=settings.chapter_target_chars,
        max_chapters=settings.max_chapters,
        output_dir=str(settings.output_dir),
        style_check=settings.style_check,
        plot_check=settings.plot_check,
    )


def load_settings(path: Path | None = None) -> Settings:
    """Load the complete configuration written by ``/setting``.

    Missing files use built-in defaults with no active model. Invalid files
    are treated the same way so the interactive UI can still open and repair
    the configuration.
    """
    try:
        user_settings = load_user_settings(path)
    except Exception:
        user_settings = None
    return settings_from_user_settings(user_settings)
