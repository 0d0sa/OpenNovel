"""Tests for the data models: validation, chapter ops, JSON persistence."""

import json

import pytest
from pydantic import ValidationError

from opennovel.memory import CharacterRecord, PlotState, StyleProfile
from opennovel.models import (
    Chapter,
    Novel,
    Scene,
    SceneStatus,
    load_novel,
    save_novel,
    save_novel_json,
)


def make_novel(**overrides) -> Novel:
    data = {
        "title": "雾中城",
        "plot": "少年进入雾城寻找失踪的妹妹。",
    }
    data.update(overrides)
    return Novel(**data)


def test_novel_defaults():
    novel = make_novel()
    assert novel.style_profile == StyleProfile()
    assert novel.plot_state == PlotState()
    assert novel.chapters == []
    assert novel.plot_state == PlotState()


def test_title_required():
    with pytest.raises(ValidationError):
        Novel()


def test_scene_status_defaults_to_planned():
    scene = Scene(summary="雨夜抵达雾城")
    assert scene.status == SceneStatus.PLANNED
    assert scene.content == ""


def test_chapter_holds_scenes():
    scene = Scene(summary="雨夜抵达雾城")
    chapter = Chapter(title="第一章", outline="抵达雾城", scenes=[scene])
    assert chapter.scenes[0].summary == "雨夜抵达雾城"


def test_add_remove_chapters():
    novel = make_novel()
    novel.chapters.append(Chapter(title="第一章"))
    assert len(novel.chapters) == 1
    novel.chapters.pop()
    assert novel.chapters == []


def test_novel_carries_style_and_plot_state():
    novel = make_novel(
        style_profile=StyleProfile(tone="冷峻"),
        plot_state=PlotState(
            characters={"林晚": CharacterRecord(name="林晚", role="主角")},
        ),
    )
    assert novel.style_profile.tone == "冷峻"
    assert novel.plot_state.characters["林晚"].role == "主角"


def test_plot_state_dict_is_required_field():
    with pytest.raises(ValidationError):
        PlotState(characters={"x": {}})


def test_json_roundtrip_preserves_everything(tmp_path):
    novel = make_novel(
        style_profile=StyleProfile(tone="冷峻", pov="第三人称限知"),
        plot_state=PlotState(
            characters={"林晚": CharacterRecord(name="林晚", role="主角", facts=["失忆"])},
        ),
        chapters=[
            Chapter(
                title="第一章",
                outline="抵达雾城",
                scenes=[Scene(summary="雨夜抵达雾城", content="雨下了一夜。", status=SceneStatus.WRITTEN)],
            )
        ],
    )
    path = save_novel(novel, tmp_path / "sub" / "novel.json")
    loaded = load_novel(path)

    assert loaded == novel
    assert loaded.chapters[0].scenes[0].content == "雨下了一夜。"
    assert loaded.plot_state.characters["林晚"].facts == ["失忆"]
    assert loaded.style_profile.pov == "第三人称限知"
    assert path.parent.exists()
    assert path.suffix == ".json"


def test_default_novel_path():
    from opennovel.models import default_novel_path

    assert str(default_novel_path("雾中城")) == "novels/雾中城/novel.json"


def test_save_novel_json_matches_model():
    novel = make_novel()
    assert json.loads(novel.model_dump_json()) == save_novel_json(novel)


def test_load_invalid_json_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(Exception):
        load_novel(bad)
