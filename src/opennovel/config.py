"""Application settings, loaded from OPENNOVEL_* env vars.

Values are read from the environment once (`load_settings`); the CLI loads
`.env` via python-dotenv before anything reads them. Novel-generation knobs
(chapter size, max chapters, language) are consumed by the orchestrator.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

ENV_API_KEY = "OPENNOVEL_LLM_API_KEY"
ENV_BASE_URL = "OPENNOVEL_LLM_BASE_URL"
ENV_MODEL = "OPENNOVEL_LLM_MODEL"
ENV_TEMPERATURE = "OPENNOVEL_LLM_TEMPERATURE"
ENV_MAX_TOKENS = "OPENNOVEL_LLM_MAX_TOKENS"
ENV_LLM_INTERVAL = "OPENNOVEL_LLM_INTERVAL"
ENV_LANGUAGE = "OPENNOVEL_LANGUAGE"
ENV_CHAPTER_TARGET_CHARS = "OPENNOVEL_CHAPTER_TARGET_CHARS"
ENV_MAX_CHAPTERS = "OPENNOVEL_MAX_CHAPTERS"
ENV_OUTPUT_DIR = "OPENNOVEL_OUTPUT_DIR"
ENV_STYLE_CHECK = "OPENNOVEL_STYLE_CHECK"
ENV_PLOT_CHECK = "OPENNOVEL_PLOT_CHECK"

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


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from env vars; missing keys fall back to defaults.

    `llm_api_key` also falls back to OPENAI_API_KEY; `llm_base_url` defaults
    to None (OpenAI official endpoint). Invalid numeric values raise ValueError.
    """
    env = os.environ if env is None else env
    return Settings(
        llm_api_key=env.get(ENV_API_KEY) or env.get("OPENAI_API_KEY") or "",
        llm_model=env.get(ENV_MODEL, ""),
        llm_base_url=env.get(ENV_BASE_URL) or None,
        llm_temperature=_float(env, ENV_TEMPERATURE, DEFAULT_TEMPERATURE),
        llm_max_tokens=_int(env, ENV_MAX_TOKENS, DEFAULT_MAX_TOKENS),
        llm_call_interval=_float(env, ENV_LLM_INTERVAL, 0.0),
        language=env.get(ENV_LANGUAGE, "zh"),
        chapter_target_chars=_int(env, ENV_CHAPTER_TARGET_CHARS, 3000),
        max_chapters=_int(env, ENV_MAX_CHAPTERS, 20),
        output_dir=Path(env.get(ENV_OUTPUT_DIR, "novels")),
        style_check=_bool(env, ENV_STYLE_CHECK, True),
        plot_check=_bool(env, ENV_PLOT_CHECK, True),
    )


def _bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "off", "no"}


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    return int(raw) if raw else default


def _float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    return float(raw) if raw else default
