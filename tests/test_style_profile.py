"""Tests for style memory: extraction, anchor block, deviation check."""

import os

import pytest

from opennovel.llm import ChatMessage, CompletionRequest, FakeProvider, LLMError
from opennovel.memory import (
    StyleDeviation,
    StyleProfile,
    check_style_deviation,
    extract_style_profile,
    style_anchor_block,
)

SAMPLE = "雨把整座城泡软了。街灯一盏盏亮起，像溺水者伸出的手。"


def profile_reply() -> str:
    return FakeProvider.json_reply(
        {
            "tone": "冷峻诗意",
            "pov": "第三人称限知",
            "tense": "过去时，冷叙事",
            "diction": "短句，密集意象",
            "sample_passage": SAMPLE,
        }
    )


def deviation_reply() -> str:
    return FakeProvider.json_reply(
        {
            "score": 3,
            "deviations": ["「哈哈这太棒了！」：语气轻佻，与冷峻基调不符"],
            "suggestion": "删去感叹句，改为克制叙述",
        }
    )


def test_extract_style_profile_returns_full_profile():
    provider = FakeProvider(replies=[profile_reply()])
    profile = extract_style_profile(provider, "少年雨夜进城寻妹", "冷峻")
    assert isinstance(profile, StyleProfile)
    assert profile.tone == "冷峻诗意"
    assert profile.sample_passage == SAMPLE
    assert provider.calls[0].messages[2].content == "剧情：少年雨夜进城寻妹\n\n风格要求：冷峻"
    assert provider.calls[0].schema is StyleProfile


def test_extract_without_hint_uses_placeholder():
    provider = FakeProvider(replies=[profile_reply()])
    extract_style_profile(provider, "剧情")
    assert "请自行设定" in provider.calls[0].messages[2].content


def test_extract_missing_sample_raises():
    provider = FakeProvider(
        replies=[FakeProvider.json_reply({"tone": "冷峻", "sample_passage": ""})]
    )
    with pytest.raises(ValueError, match="sample_passage"):
        extract_style_profile(provider, "剧情")


def test_anchor_block_contains_fields_and_sample():
    profile = StyleProfile(tone="冷峻", pov="第三人称限知", diction="短句", sample_passage=SAMPLE)
    block = style_anchor_block(profile)
    assert "文风基调：冷峻" in block
    assert "视角人称：第三人称限知" in block
    assert "用语特点：短句" in block
    assert SAMPLE in block
    assert "叙事时态" not in block  # empty fields are skipped


def test_check_style_deviation_parses():
    provider = FakeProvider(replies=[deviation_reply()])
    profile = StyleProfile(tone="冷峻", sample_passage=SAMPLE)
    result = check_style_deviation(provider, profile, "章节正文……")
    assert isinstance(result, StyleDeviation)
    assert result.score == 3
    assert result.deviations
    assert "克制" in result.suggestion
    assert provider.calls[0].schema is StyleDeviation


def test_check_deviation_invalid_score_rejected():
    provider = FakeProvider(replies=[FakeProvider.json_reply({"score": 9})])
    with pytest.raises(LLMError):
        check_style_deviation(provider, StyleProfile(tone="冷峻"), "正文")


@pytest.mark.skipif(
    not (os.environ.get("OPENNOVEL_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="requires real API key",
)
def test_real_extraction_smoke():
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(".env"))
    from opennovel.llm import provider_from_env

    provider = provider_from_env()
    profile = extract_style_profile(provider, "雨夜，少年抵达雾城寻找失踪的妹妹。", "冷峻克制")
    assert profile.sample_passage
    print(f"\nprofile: {profile.model_dump()}")
