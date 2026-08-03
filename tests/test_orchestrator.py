"""End-to-end tests for the orchestration pipeline (with FakeProvider)."""

import os
from dataclasses import replace
from pathlib import Path

import pytest

from opennovel.agent import write_novel
from opennovel.config import Settings
from opennovel.llm import FakeProvider
from opennovel.memory import StyleDeviation, PlotConsistency
from opennovel.models import Novel, SceneStatus

PLOT = "少年林晚雨夜抵达雾城寻找失踪的妹妹。"


def style_profile_reply() -> str:
    return FakeProvider.json_reply(
        {
            "tone": "冷峻",
            "pov": "第三人称限知",
            "diction": "短句",
            "sample_passage": "雨落了一夜。",
        }
    )


def chapter_plans_reply() -> str:
    return FakeProvider.json_reply(
        {
            "chapters": [
                {"title": "抵达", "focus": "林晚进城，遇到陈默", "scene_count": 2},
                {"title": "旧公寓", "focus": "找到妹妹线索", "scene_count": 2},
            ]
        }
    )


def scenes_reply(*summaries: str) -> str:
    return FakeProvider.json_reply(
        {"scenes": [{"summary": s} for s in summaries]}
    )


def ok_update_reply() -> str:
    return FakeProvider.json_reply(
        {
            "new_characters": [{"name": "林晚", "role": "主角", "facts": ["来自山南镇"]}],
            "events": [],
            "new_setups": [],
            "resolved_setups": [],
        }
    )


def ok_style_reply() -> str:
    return FakeProvider.json_reply({"score": 0, "deviations": [], "suggestion": ""})


def ok_plot_reply() -> str:
    return FakeProvider.json_reply({"score": 0, "contradictions": [], "suggestion": ""})


def settings(tmp_path: Path) -> Settings:
    return replace(
        Settings(),
        output_dir=tmp_path,
        max_chapters=2,
        chapter_target_chars=400,
    )


def test_write_novel_full_pipeline(tmp_path):
    provider = FakeProvider()
    provider.enqueue(
        style_profile_reply(),
        chapter_plans_reply(),
        scenes_reply("雨夜下车", "车站相遇"),
        "雨下了一夜，林晚下车。",
        "车站里，陈默打量着少年。",
        ok_style_reply(),
        ok_plot_reply(),
        ok_update_reply(),
        scenes_reply("循信找到公寓", "门后有人"),
        "林晚循着信找到旧公寓。",
        "门后响起脚步声。",
        ok_style_reply(),
        ok_plot_reply(),
        ok_update_reply(),
    )

    novel = write_novel(provider, settings(tmp_path), "雾中城", PLOT, "冷峻")

    assert isinstance(novel, Novel)
    assert len(novel.chapters) == 2
    assert novel.chapters[0].title == "抵达"
    assert all(s.status == SceneStatus.WRITTEN and s.content for s in novel.chapters[0].scenes)
    assert novel.plot_state.characters["林晚"].facts == ["来自山南镇"]
    assert (tmp_path / "雾中城" / "novel.json").exists()
    txt = (tmp_path / "雾中城" / "novel.txt").read_text(encoding="utf-8")
    assert "第1章 抵达" in txt
    assert "雨下了一夜" in txt


def test_write_novel_rewrites_when_checks_fail(tmp_path):
    provider = FakeProvider()
    bad_style = FakeProvider.json_reply(
        {"score": 4, "deviations": ["语气轻佻"], "suggestion": "改为克制叙述"}
    )
    provider.enqueue(
        style_profile_reply(),
        chapter_plans_reply(),
        scenes_reply("雨夜下车"),
        "雨下了一夜，林晚下车。",
        bad_style,
        ok_plot_reply(),
        "重写后的正文：语气克制。",
        ok_update_reply(),
    )

    novel = write_novel(provider, replace(settings(tmp_path), max_chapters=1), "雾中城", PLOT)

    chapter = novel.chapters[0]
    assert len(chapter.scenes) == 1  # collapsed into a rewritten chapter
    assert chapter.scenes[0].status == SceneStatus.WRITTEN
    assert "重写后的正文" in chapter.scenes[0].content
    assert novel.plot_state.characters["林晚"].role == "主角"


def test_write_novel_respects_max_chapters(tmp_path):
    provider = FakeProvider()
    provider.enqueue(
        style_profile_reply(),
        chapter_plans_reply(),
        scenes_reply("雨夜下车"),
        "正文",
        ok_style_reply(),
        ok_plot_reply(),
        ok_update_reply(),
    )
    s = replace(settings(tmp_path), max_chapters=1)
    novel = write_novel(provider, s, "雾中城", PLOT)
    assert len(novel.chapters) == 1


@pytest.mark.skipif(
    not (os.environ.get("OPENNOVEL_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="requires real API key",
)
def test_real_write_small_novel(tmp_path):
    from pathlib import Path as P

    from dotenv import load_dotenv

    load_dotenv(P(".env"))
    from opennovel.llm import provider_from_env

    provider = provider_from_env()
    s = replace(
        Settings(),
        output_dir=tmp_path,
        max_chapters=1,
        chapter_target_chars=300,
    )
    novel = write_novel(
        provider, s, "雾中城测试", "少年雨夜进城找妹妹。", "冷峻", on_progress=print
    )
    assert len(novel.chapters) == 1
    assert novel.chapters[0].scenes[0].content
    assert (tmp_path / "雾中城测试" / "novel.json").exists()
    print("\nchapter:", novel.chapters[0].title)
    print(novel.chapters[0].scenes[0].content)
