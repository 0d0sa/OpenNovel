"""Tests for the v2 base tool set (读取/提取/编写/修改/保存/检查)."""

from dataclasses import replace
from pathlib import Path

import pytest

from opennovel.agent import ToolContext, ToolError, tool_catalog
from opennovel.agent.tools import run_tool
from opennovel.config import Settings
from opennovel.llm import FakeProvider
from opennovel.memory import StyleProfile
from opennovel.models import (
    Chapter,
    ChapterPlan,
    Novel,
    Scene,
    SceneStatus,
)


def make_ctx(provider, tmp_path: Path, *, title="雾中城", plot="少年进城找妹妹。", novel=None, **kwargs):
    return ToolContext(
        provider=provider,
        settings=replace(Settings(), output_dir=tmp_path, chapter_target_chars=200),
        title=title,
        plot=plot,
        novel=novel,
        **kwargs,
    )


def scenes_reply(*summaries: str) -> str:
    return FakeProvider.json_reply({"scenes": [{"summary": s} for s in summaries]})


def ok_style_reply() -> str:
    return FakeProvider.json_reply({"score": 0, "deviations": [], "suggestion": ""})


def ok_plot_reply() -> str:
    return FakeProvider.json_reply({"score": 0, "contradictions": [], "suggestion": ""})


def ok_update_reply() -> str:
    return FakeProvider.json_reply(
        {
            "new_characters": [{"name": "林晚", "role": "主角", "facts": ["来自山南镇"]}],
            "events": [],
            "new_setups": [],
            "resolved_setups": [],
        }
    )


def seeded_novel(**kwargs) -> Novel:
    novel = Novel(title="雾中城", plot="少年进城找妹妹。", **kwargs)
    novel.style_profile = StyleProfile(
        tone="冷峻", pov="第三人称限知", sample_passage="雨落了一夜。"
    )
    novel.outline = [
        ChapterPlan(title="夜雨", focus="进城遇到陈默", scene_count=1),
        ChapterPlan(title="旧公寓", focus="找到妹妹线索", scene_count=1),
    ]
    return novel


# --- catalog ---


def test_tool_catalog_lists_all_categories():
    catalog = tool_catalog()
    for name in (
        "list_books", "read_status", "extract_style", "plan_outline",
        "write_chapter", "write_scene", "continue_writing",
        "rewrite_chapter", "edit_chapter", "append_plot",
        "save", "export_txt", "check_style", "check_plot", "update_plot_state",
    ):
        assert f"- {name}" in catalog


def test_run_unknown_tool_raises(tmp_path):
    ctx = make_ctx(FakeProvider(), tmp_path)
    with pytest.raises(ToolError, match="未知工具"):
        run_tool("no_such_tool", {}, ctx)


# --- 读取 ---


def test_read_status_and_chapter(tmp_path):
    novel = Novel(
        title="雾中城",
        plot="剧情",
        chapters=[
            Chapter(
                title="夜雨",
                outline="进城",
                scenes=[Scene(summary="s", content="正文内容", status=SceneStatus.WRITTEN)],
            )
        ],
    )
    ctx = make_ctx(FakeProvider(), tmp_path, novel=novel)
    out = run_tool("read_status", {}, ctx)
    assert "夜雨" in out.summary
    assert "大纲 2 章" in out.summary or "大纲 0 章" in out.summary
    out = run_tool("read_chapter", {"chapter_no": 1}, ctx)
    assert "正文内容" in out.summary
    with pytest.raises(ToolError, match="超出范围"):
        run_tool("read_chapter", {"chapter_no": 2}, ctx)


def test_read_plot_and_style(tmp_path):
    novel = Novel(title="雾中城", plot="少年进城找妹妹。")
    novel.style_profile = StyleProfile(tone="冷峻", pov="第三人称限知", sample_passage="雨落了一夜。")
    ctx = make_ctx(FakeProvider(), tmp_path, novel=novel)
    assert "少年进城" in run_tool("read_plot", {}, ctx).summary
    out = run_tool("read_style", {}, ctx).summary
    assert "冷峻" in out and "第三人称" in out


def test_list_books_scans_disk(tmp_path):
    (tmp_path / "雾中城").mkdir()
    novel = Novel(title="雾中城", plot="剧情")
    novel.chapters.append(
        Chapter(title="夜雨", scenes=[Scene(summary="s", content="正文", status=SceneStatus.WRITTEN)])
    )
    from opennovel.models import save_novel

    save_novel(novel, tmp_path / "雾中城" / "novel.json")
    ctx = make_ctx(FakeProvider(), tmp_path)
    out = run_tool("list_books", {}, ctx).summary
    assert "《雾中城》" in out and "1 章" in out


# --- 修改 / 保存 ---


def test_append_plot_creates_book_on_disk(tmp_path):
    ctx = make_ctx(FakeProvider(), tmp_path)
    result = run_tool("append_plot", {"text": "他在车站遇见老警察。"}, ctx)
    assert "已追加到剧情" in result.summary
    assert ctx.novel is not None
    assert (tmp_path / "雾中城" / "novel.json").exists()
    ctx2 = make_ctx(FakeProvider(), tmp_path)
    assert "老警察" in ctx2.fresh_novel().plot


def test_append_plot_requires_title(tmp_path):
    ctx = make_ctx(FakeProvider(), tmp_path, title="")
    with pytest.raises(ToolError, match="书名"):
        run_tool("append_plot", {"text": "x"}, ctx)


def test_rewrite_chapter_with_instructions(tmp_path):
    novel = Novel(
        title="雾中城",
        plot="剧情",
        chapters=[
            Chapter(
                title="夜雨",
                scenes=[Scene(summary="s", content="旧正文", status=SceneStatus.WRITTEN)],
            )
        ],
    )
    provider = FakeProvider(replies=["更紧张的重写稿"])
    ctx = make_ctx(provider, tmp_path, novel=novel)
    result = run_tool("rewrite_chapter", {"chapter_no": 1, "instructions": "写得更紧张"}, ctx)
    assert "已重写" in result.summary
    assert novel.chapters[0].scenes[0].content == "更紧张的重写稿"
    assert novel.chapters[0].style_report is None


def test_edit_chapter_targeted(tmp_path):
    novel = Novel(
        title="雾中城",
        plot="剧情",
        chapters=[
            Chapter(
                title="夜雨",
                scenes=[Scene(summary="s", content="旧正文", status=SceneStatus.WRITTEN)],
            )
        ],
    )
    provider = FakeProvider(replies=["改好后的正文"])
    ctx = make_ctx(provider, tmp_path, novel=novel)
    result = run_tool("edit_chapter", {"chapter_no": 1, "instructions": "开头改成雨夜"}, ctx)
    assert "已按指示修改" in result.summary
    assert ctx.novel.chapters[0].scenes[0].content == "改好后的正文"


def test_save_and_export_txt(tmp_path):
    novel = Novel(
        title="雾中城",
        plot="剧情",
        chapters=[
            Chapter(
                title="夜雨",
                scenes=[Scene(summary="s", content="正文", status=SceneStatus.WRITTEN)],
            )
        ],
    )
    ctx = make_ctx(FakeProvider(), tmp_path, novel=novel)
    assert "已保存" in run_tool("save", {}, ctx).summary
    result = run_tool("export_txt", {}, ctx)
    assert "已导出" in result.summary
    assert (tmp_path / "雾中城" / "novel.txt").exists()
    with pytest.raises(ToolError, match="章节"):
        run_tool("export_txt", {}, make_ctx(FakeProvider(), tmp_path, novel=Novel(title="空", plot="")))


# --- 提取 ---


def test_plan_outline_and_scenes(tmp_path):
    novel = Novel(title="雾中城", plot="剧情")
    provider = FakeProvider(
        replies=[
            FakeProvider.json_reply(
                {"chapters": [{"title": "夜雨", "focus": "进城", "scene_count": 2}]}
            )
        ]
    )
    ctx = make_ctx(provider, tmp_path, novel=novel)
    result = run_tool("plan_outline", {"max_chapters": 5}, ctx)
    assert "夜雨" in result.summary
    assert len(ctx.novel.outline) == 1
    provider.enqueue(scenes_reply("雨夜下车", "车站相遇"))
    result = run_tool("plan_scenes", {"chapter_no": 1}, ctx)
    assert "场景1" in result.summary
    assert ctx.novel.chapters[0].scenes[0].summary == "雨夜下车"
    assert ctx.novel.chapters[0].scenes[0].status == SceneStatus.PLANNED


def test_update_plot_state_tool(tmp_path):
    novel = Novel(
        title="雾中城",
        plot="剧情",
        chapters=[
            Chapter(
                title="夜雨",
                scenes=[Scene(summary="s", content="林晚走进车站。", status=SceneStatus.WRITTEN)],
            )
        ],
    )
    provider = FakeProvider(replies=[ok_update_reply()])
    ctx = make_ctx(provider, tmp_path, novel=novel)
    result = run_tool("update_plot_state", {"chapter_no": 1}, ctx)
    assert "剧情状态已更新" in result.summary
    assert novel.plot_state.characters["林晚"].role == "主角"


# --- 编写 ---


def test_write_chapter_full_flow(tmp_path):
    novel = seeded_novel()
    provider = FakeProvider(
        replies=[
            scenes_reply("雨夜下车"),
            "雨下了一夜，林晚下车。",
            ok_style_reply(),
            ok_plot_reply(),
            ok_update_reply(),
        ]
    )
    tokens: list[str] = []
    ctx = make_ctx(provider, tmp_path, novel=novel, on_token=tokens.append)
    result = run_tool("write_chapter", {"chapter_no": 0}, ctx)
    assert "第1章" in result.summary
    assert "风格检查 0/5" in result.summary
    assert len(novel.chapters) == 1
    assert novel.chapters[0].scenes[0].content == "雨下了一夜，林晚下车。"
    assert novel.plot_state.characters["林晚"].role == "主角"
    assert tokens == ["雨下了一夜，林晚下车。"]
    assert (tmp_path / "雾中城" / "novel.json").exists()


def test_write_chapter_reuses_planned_scenes(tmp_path):
    novel = seeded_novel()
    novel.chapters.append(
        Chapter(
            title="夜雨",
            outline="进城",
            scenes=[Scene(summary="雨夜下车", status=SceneStatus.PLANNED)],
        )
    )
    provider = FakeProvider(
        replies=[
            "雨下了一夜，林晚下车。",
            ok_style_reply(),
            ok_plot_reply(),
            ok_update_reply(),
        ]
    )
    ctx = make_ctx(provider, tmp_path, novel=novel)
    result = run_tool("write_chapter", {"chapter_no": 1}, ctx)
    assert "第1章" in result.summary
    assert novel.chapters[0].scenes[0].content == "雨下了一夜，林晚下车。"


def test_write_chapter_rejects_existing(tmp_path):
    novel = seeded_novel()
    novel.chapters.append(
        Chapter(
            title="夜雨",
            scenes=[Scene(summary="s", content="已有正文", status=SceneStatus.WRITTEN)],
        )
    )
    ctx = make_ctx(FakeProvider(), tmp_path, novel=novel)
    with pytest.raises(ToolError, match="已有正文"):
        run_tool("write_chapter", {"chapter_no": 1}, ctx)


def test_write_chapter_out_of_outline(tmp_path):
    novel = Novel(title="雾中城", plot="剧情")
    novel.style_profile = StyleProfile(tone="冷峻", sample_passage="雨落了一夜。")
    novel.outline = [ChapterPlan(title="夜雨", focus="进城")]
    ctx = make_ctx(FakeProvider(), tmp_path, novel=novel)
    with pytest.raises(ToolError, match="超出大纲范围"):
        run_tool("write_chapter", {"chapter_no": 2}, ctx)


def test_write_scene_fills_planned(tmp_path):
    novel = Novel(
        title="雾中城",
        plot="剧情",
        chapters=[
            Chapter(
                title="夜雨",
                scenes=[Scene(summary="雨夜下车", status=SceneStatus.PLANNED)],
            )
        ],
    )
    provider = FakeProvider(replies=["车站的雨很大。"])
    tokens: list[str] = []
    ctx = make_ctx(provider, tmp_path, novel=novel, on_token=tokens.append)
    result = run_tool("write_scene", {"chapter_no": 1, "scene_no": 1}, ctx)
    assert "已写" in result.summary
    assert novel.chapters[0].scenes[0].content == "车站的雨很大。"
    assert tokens == ["车站的雨很大。"]


def test_continue_writing_multiple_chapters(tmp_path):
    novel = seeded_novel()
    provider = FakeProvider(
        replies=[
            scenes_reply("雨夜下车"),
            "第一章正文。",
            ok_style_reply(),
            ok_plot_reply(),
            ok_update_reply(),
            scenes_reply("循信找公寓"),
            "第二章正文。",
            ok_style_reply(),
            ok_plot_reply(),
            ok_update_reply(),
        ]
    )
    ctx = make_ctx(provider, tmp_path, novel=novel)
    result = run_tool("continue_writing", {"chapters": 2}, ctx)
    assert "第1章" in result.summary
    assert "第2章" in result.summary
    assert len(ctx.novel.chapters) == 2


# --- 检查 ---


def test_check_tools_write_reports(tmp_path):
    novel = Novel(
        title="雾中城",
        plot="剧情",
        chapters=[
            Chapter(
                title="夜雨",
                scenes=[Scene(summary="s", content="正文", status=SceneStatus.WRITTEN)],
            )
        ],
    )
    provider = FakeProvider(replies=[ok_style_reply(), ok_plot_reply()])
    ctx = make_ctx(provider, tmp_path, novel=novel)
    result = run_tool("check_style", {"chapter_no": 1}, ctx)
    assert "0/5" in result.summary
    assert ctx.novel.chapters[0].style_report is not None
    result = run_tool("check_plot", {"chapter_no": 1}, ctx)
    assert "0/5" in result.summary
    assert ctx.novel.chapters[0].plot_report is not None
