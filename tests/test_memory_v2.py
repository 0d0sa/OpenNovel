"""Tests for memory v2: memory.json store + migration + retrieval + briefs."""

from dataclasses import replace
from pathlib import Path

from opennovel.agent import ToolContext
from opennovel.config import Settings
from opennovel.llm import FakeProvider
from opennovel.memory import CharacterRecord, search_memory, split_sentences
from opennovel.memory.plot_state import ChapterSummary
from opennovel.models import (
    Chapter,
    Novel,
    NovelMemory,
    Scene,
    SceneStatus,
    default_memory_path,
    load_memory,
    save_memory,
)
from opennovel.models.memory_store import save_memory as save_memory_at


def make_ctx(tmp_path: Path, *, novel: Novel | None = None, title="雾中城", plot="剧情"):
    return ToolContext(
        provider=FakeProvider(),
        settings=replace(Settings(), output_dir=tmp_path),
        title=title,
        plot=plot,
        novel=novel,
    )


def test_memory_store_roundtrip(tmp_path):
    mem = NovelMemory()
    mem.chapter_summaries.append(
        ChapterSummary(chapter_no=1, title="夜雨", overview="进城", hook="拆信")
    )
    path = save_memory(mem, default_memory_path("雾中城", tmp_path))
    assert path.exists()
    loaded = load_memory("雾中城", tmp_path)
    assert loaded is not None
    assert loaded.chapter_summaries[0].overview == "进城"
    assert loaded.version == 2


def test_fresh_memory_migrates_from_novel(tmp_path):
    novel = Novel(title="雾中城", plot="剧情")
    novel.style_profile.tone = "冷峻"
    novel.plot_state.characters["林晚"] = CharacterRecord(name="林晚", role="主角")
    ctx = make_ctx(tmp_path, novel=novel)
    memory = ctx.fresh_memory()
    assert memory is not None
    assert memory.style_profile.tone == "冷峻"
    assert memory.plot_state.characters["林晚"].role == "主角"
    assert default_memory_path("雾中城", tmp_path).exists()
    # 再次调用不替换 ctx.novel
    ctx.fresh_memory()
    assert ctx.novel is novel


def test_split_sentences_and_search(tmp_path):
    novel = Novel(title="雾中城", plot="剧情")
    novel.chapters.append(
        Chapter(
            title="夜雨",
            scenes=[
                Scene(summary="s", content="雨下了一夜，林晚在车站下车。陈默远远看着他。", status=SceneStatus.WRITTEN)
            ],
        )
    )
    sentences = split_sentences("雨下了一夜，林晚在车站下车。陈默远远看着他。")
    assert len(sentences) == 2
    assert sentences[0].startswith("雨下了")

    memory = NovelMemory()
    memory.plot_state.characters["林晚"] = CharacterRecord(name="林晚", role="主角")
    memory.chapter_summaries.append(
        ChapterSummary(chapter_no=1, title="夜雨", overview="进城", hook="拆信")
    )
    hits = search_memory(novel, memory, "陈默", limit=5)
    assert hits and "陈默" in hits[0]
    hits = search_memory(novel, memory, "不存在的词", limit=5)
    assert hits == []
    # 角色词典：按角色名检索
    hits = search_memory(novel, memory, "林晚", limit=5)
    assert hits
