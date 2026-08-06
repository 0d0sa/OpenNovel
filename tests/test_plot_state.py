"""Tests for plot memory: incremental update/merge, brief, consistency check."""


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
from tests._realapi import REAL_API_AVAILABLE

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


# --- v2: relation-annotated merge ---


def relation_reply(**overrides) -> str:
    payload = {
        "new_characters": [],
        "events": [],
        "new_setups": [],
        "resolved_setups": [],
    }
    payload.update(overrides)
    return FakeProvider.json_reply(payload)


def test_duplicate_event_is_dropped():
    state = state_with()
    provider = FakeProvider(
        replies=[
            relation_reply(
                events=[{"summary": "抵达雾城", "involved": ["林晚"], "relation": "duplicate_of", "target": "抵达雾城"}]
            )
        ]
    )
    result = update_plot_state(provider, CH2, 2, state)
    assert len(result.events) == 1  # 未重复追加
    assert result.events[0].chapter == 1


def test_extends_event_merges_involved():
    state = state_with()
    provider = FakeProvider(
        replies=[
            relation_reply(
                events=[{"summary": "抵达雾城", "involved": ["陈默"], "relation": "extends", "target": "抵达雾城"}]
            )
        ]
    )
    result = update_plot_state(provider, CH2, 2, state)
    assert len(result.events) == 1
    assert result.events[0].involved == ["林晚", "陈默"]


def test_update_facts_matches_by_paraphrase():
    state = state_with(CharacterRecord(name="林晚", role="主角", facts=["抵达雾城"]))
    provider = FakeProvider(
        replies=[
            relation_reply(
                new_characters=[
                    {"name": "主角", "facts": ["来自山南镇"], "relation": "update_facts", "target": "林晚"}
                ]
            )
        ]
    )
    result = update_plot_state(provider, CH2, 2, state)
    assert result.characters["林晚"].facts == ["抵达雾城", "来自山南镇"]


def test_update_role_overrides_role():
    state = state_with(CharacterRecord(name="林晚", role="主角", facts=["失忆"]))
    provider = FakeProvider(
        replies=[
            relation_reply(
                new_characters=[
                    {"name": "林晚", "role": "侦探", "relation": "update_role", "target": "林晚"}
                ]
            )
        ]
    )
    result = update_plot_state(provider, CH2, 2, state)
    assert result.characters["林晚"].role == "侦探"
    assert result.characters["林晚"].facts == ["失忆"]  # facts 不受 update_role 影响


def test_setup_resolved_by_relation_semantic_match():
    state = state_with()  # setups: 站台角落的信（第1章）
    provider = FakeProvider(
        replies=[
            relation_reply(
                new_setups=[{"description": "林晚拿起了那封信", "relation": "resolved", "target": "站台角落的信"}]
            )
        ]
    )
    result = update_plot_state(provider, CH2, 2, state)
    assert result.setups[0].resolved_in == 2
    assert len(result.setups) == 1  # 未追加新伏笔


def test_unmatched_resolution_degrades_to_new_setup():
    state = state_with()
    provider = FakeProvider(
        replies=[
            relation_reply(
                new_setups=[{"description": "一封全新的信", "relation": "resolved", "target": "不存在的伏笔"}]
            )
        ]
    )
    result = update_plot_state(provider, CH2, 2, state)
    assert result.setups[0].resolved_in is None  # 旧伏笔未被误标
    assert result.setups[-1].description == "一封全新的信"
    assert result.setups[-1].resolved_in is None  # 保守降级为新伏笔


def test_update_memory_extracts_summary():
    provider = FakeProvider(
        replies=[
            relation_reply(
                new_characters=[{"name": "林晚", "role": "主角"}],
                chapter_summary={
                    "overview": "林晚抵达雾城",
                    "events": ["车站相遇"],
                    "new_characters": ["林晚"],
                    "hook": "下一章要拆开那封信",
                },
            )
        ]
    )
    from opennovel.memory import update_memory

    state, summary = update_memory(provider, CH1, 1, PlotState(), chapter_title="夜雨")
    assert state.characters["林晚"].role == "主角"
    assert summary is not None
    assert summary.chapter_no == 1
    assert summary.title == "夜雨"
    assert summary.overview == "林晚抵达雾城"
    assert summary.hook == "下一章要拆开那封信"


def test_brief_without_setups():
    state = state_with()
    brief = plot_state_brief(state, include_setups=False)
    assert "站台角落的信" not in brief
    assert "第1章 抵达雾城" in brief


def test_semantic_match_norm():
    from opennovel.memory import semantic_match

    assert semantic_match("站台角落的信", ["站台角落的信"]) == "站台角落的信"
    assert semantic_match("角落的信", ["站台角落的信"]) == "站台角落的信"  # 子串
    assert semantic_match("站台角落发现的那封信", ["站台角落的信"]) == "站台角落的信"  # 高重合
    assert semantic_match("完全无关的内容", ["站台角落的信"]) is None
    assert semantic_match("", ["站台角落的信"]) is None


def test_two_chapter_loop_with_fake_provider():
    provider = FakeProvider()
    provider.enqueue(update_reply())
    provider.enqueue(consistency_reply())

    state = PlotState()
    state = update_plot_state(provider, CH1, 1, state)
    result = check_plot_consistency(provider, state, CH2, 2)

    assert result.score >= 0
    assert state.characters["陈默"].role == "老警察"


@pytest.mark.skipif(not REAL_API_AVAILABLE, reason="requires configured profile (run /setting)")
def test_real_update_and_check_smoke():
    from opennovel.llm import provider_from_settings

    provider = provider_from_settings()
    state = PlotState()
    state = update_plot_state(provider, CH1, 1, state)
    assert state.characters
    result = check_plot_consistency(provider, state, CH2, 2)
    print(f"\nstate: {state.model_dump()}\ncheck: {result.model_dump()}")
