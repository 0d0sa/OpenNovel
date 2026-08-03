"""Tests for plot memory: incremental update/merge, brief, consistency check."""

import os

import pytest

from opennovel.llm import FakeProvider
from opennovel.memory import (
    CharacterRecord,
    EventRecord,
    PlotConsistency,
    PlotState,
    PlotStateUpdate,
    SetupRecord,
    check_plot_consistency,
    plot_state_brief,
    update_plot_state,
)

CH1 = "少年林晚抵达雾城，在车站与老警察陈默相遇。他注意到站台角落一封信。"
CH2 = "林晚循着信上的地址找到旧公寓，陈默告诉他妹妹两年前来过这里。"


def state_with(character: CharacterRecord | None = None) -> PlotState:
    return PlotState(
        characters={character.name: character} if character else {},
        events=[EventRecord(summary="抵达雾城", chapter=1, involved=["林晚"])],
        setups=[SetupRecord(description="站台角落的信", chapter=1)],
    )


def update_reply() -> str:
    return FakeProvider.json_reply(
        {
            "new_characters": [
                {"name": "林晚", "role": "主角", "facts": ["来自山南镇"]},
                {"name": "陈默", "role": "老警察", "facts": ["在雾城任职三十年"]},
            ],
            "events": [
                {"summary": "找到旧公寓", "involved": ["林晚"]},
            ],
            "new_setups": [{"description": "妹妹两年前来过旧公寓"}],
            "resolved_setups": ["站台角落的信"],
        }
    )


def consistency_reply() -> str:
    return FakeProvider.json_reply(
        {
            "score": 2,
            "contradictions": ["「妹妹两年前来过」与第1章『林晚从未收到妹妹消息』冲突"],
            "suggestion": "改为：妹妹失踪前曾到过旧公寓",
        }
    )


def test_merge_adds_characters_events_setups_and_resolves():
    provider = FakeProvider(replies=[update_reply()])
    state = state_with(CharacterRecord(name="林晚", role="主角", facts=["抵达雾城"]))
    result = update_plot_state(provider, CH2, 2, state)

    assert result.characters["林晚"].facts == ["抵达雾城", "来自山南镇"]  # appended, not overwritten
    assert result.characters["陈默"].role == "老警察"
    assert result.events[-1].summary == "找到旧公寓"
    assert result.events[-1].chapter == 2
    assert result.setups[-1].description == "妹妹两年前来过旧公寓"
    assert result.setups[-1].resolved_in is None
    assert result.setups[0].resolved_in == 2  # old setup resolved in chapter 2
    assert provider.calls[0].schema is PlotStateUpdate


def test_merge_does_not_overwrite_existing_character():
    provider = FakeProvider(replies=[update_reply()])
    state = state_with(CharacterRecord(name="林晚", role="主角", facts=["来自山南镇"]))
    result = update_plot_state(provider, CH1, 1, state)
    assert result.characters["林晚"].facts == ["来自山南镇"]


def test_brief_contains_unresolved_setup_flag():
    state = PlotState(
        characters={"林晚": CharacterRecord(name="林晚", role="主角", facts=["失忆"])},
        events=[EventRecord(summary="抵达雾城", chapter=1)],
        setups=[
            SetupRecord(description="站台角落的信", chapter=1),
            SetupRecord(description="旧公寓门牌", chapter=1, resolved_in=2),
        ],
    )
    brief = plot_state_brief(state)
    assert "林晚（主角）：失忆" in brief
    assert "第1章 抵达雾城" in brief
    assert "待回收伏笔" in brief
    assert "站台角落的信" in brief
    assert "旧公寓门牌" not in brief


def test_brief_truncates():
    state = PlotState(
        characters={"林晚": CharacterRecord(name="林晚", role="主角", facts=["x" * 1000])}
    )
    brief = plot_state_brief(state, max_chars=200)
    assert len(brief) <= 200 + 10
    assert "（截断）" in brief


def test_check_consistency_parses():
    provider = FakeProvider(replies=[consistency_reply()])
    result = check_plot_consistency(provider, state_with(), CH2, 2)
    assert isinstance(result, PlotConsistency)
    assert result.score == 2
    assert result.contradictions
    assert "旧公寓" in result.suggestion
    assert provider.calls[0].schema is PlotConsistency


def test_two_chapter_loop_with_fake_provider():
    provider = FakeProvider()
    provider.enqueue(update_reply())
    provider.enqueue(consistency_reply())

    state = PlotState()
    state = update_plot_state(provider, CH1, 1, state)
    result = check_plot_consistency(provider, state, CH2, 2)

    assert result.score >= 0
    assert state.characters["陈默"].role == "老警察"


@pytest.mark.skipif(
    not (os.environ.get("OPENNOVEL_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="requires real API key",
)
def test_real_update_and_check_smoke():
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(".env"))
    from opennovel.llm import provider_from_env

    provider = provider_from_env()
    state = PlotState()
    state = update_plot_state(provider, CH1, 1, state)
    assert state.characters
    result = check_plot_consistency(provider, state, CH2, 2)
    print(f"\nstate: {state.model_dump()}\ncheck: {result.model_dump()}")
