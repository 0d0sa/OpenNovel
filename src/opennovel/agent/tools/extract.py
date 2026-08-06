"""提取类工具：风格档案、全书大纲、场景规划、剧情状态与章节摘要（v2 base tool set）。"""

from __future__ import annotations

from opennovel.agent.planning import ChapterPlan, plan_chapters, plan_scenes
from opennovel.agent.tools import ToolContext, ToolError, tool
from opennovel.memory import (
    extract_style_profile,
    plot_state_brief,
    style_anchor_block,
    update_memory,
)
from opennovel.models import Chapter, Novel


def _ensure_book(ctx: ToolContext) -> Novel:
    """Load or create the current book; requires title and plot."""
    if not ctx.title:
        raise ToolError("还没有书名，先告诉我书名与剧情")
    novel = ctx.fresh_novel()
    if novel is None:
        if not ctx.plot:
            raise ToolError("还没有剧情，先告诉我你想写什么故事")
        novel = Novel(title=ctx.title, plot=ctx.plot)
        ctx.novel = novel
    elif not novel.plot:
        novel.plot = ctx.plot
    return novel


def _state_brief(ctx: ToolContext, novel: Novel) -> str:
    memory = ctx.memory if ctx.memory is not None else ctx.fresh_memory()
    state = memory.plot_state if memory is not None else novel.plot_state
    return plot_state_brief(state)


@tool("extract_style", "提取/刷新当前书的统一风格档案（开写前应调用一次）", category="提取")
def extract_style(ctx: ToolContext, style_hint: str = "") -> str:
    novel = _ensure_book(ctx)
    hint = style_hint.strip() or ctx.style_hint
    profile = extract_style_profile(ctx.provider, novel.plot, hint)
    novel.style_profile = profile
    memory = ctx.fresh_memory()
    if memory is not None:
        memory.style_profile = profile
        ctx.save_memory()
    ctx.save()
    return (
        f"风格档案已提取并保存：文风 {profile.tone}；视角 {profile.pov}；"
        f"用语 {profile.diction}。后续写作都会遵守该锚点。"
    )


@tool("plan_outline", "规划并保存全书章节大纲（续写前应调用一次）", category="提取")
def plan_outline(ctx: ToolContext, max_chapters: int = 0) -> str:
    novel = _ensure_book(ctx)
    limit = max_chapters if max_chapters > 0 else ctx.settings.max_chapters
    plans = plan_chapters(ctx.provider, novel.plot, limit)
    novel.outline = plans
    ctx.save()
    lines = [f"全书大纲已规划并保存（共 {len(plans)} 章）："]
    for i, p in enumerate(plans, 1):
        lines.append(f"- 第{i}章 {p.title}：{p.focus}")
    return "\n".join(lines)


@tool("plan_scenes", "为指定章节规划场景大纲（scene_no 供后续逐场景写作）", category="提取")
def plan_scenes_tool(ctx: ToolContext, chapter_no: int) -> str:
    novel = _ensure_book(ctx)
    idx = chapter_no
    if idx <= 0 or idx > len(novel.chapters) + 1:
        raise ToolError(f"章节号超出范围（1-{len(novel.chapters) + 1}）")
    if idx <= len(novel.chapters) and any(s.content for s in novel.chapters[idx - 1].scenes):
        raise ToolError(f"第{idx}章已有正文，不需要再规划场景")
    plan = _plan_for(novel, idx)
    anchor = style_anchor_block(novel.style_profile)
    brief = _state_brief(ctx, novel)
    scenes = plan_scenes(ctx.provider, novel.plot, plan, anchor, brief)
    if not scenes:
        raise ToolError("场景规划返回为空，请重试")
    chapter = Chapter(title=plan.title, outline=plan.focus, scenes=scenes)
    if idx <= len(novel.chapters):
        novel.chapters[idx - 1] = chapter
    else:
        novel.chapters.append(chapter)
    ctx.save()
    lines = [f"第{idx}章《{plan.title}》场景大纲（共 {len(scenes)} 个）："]
    for i, s in enumerate(scenes, 1):
        lines.append(f"- 场景{i}：{s.summary}")
    lines.append("确认后可用 write_scene 逐场景写作，或直接用 write_chapter 一次写完。")
    return "\n".join(lines)


@tool(
    "update_plot_state",
    "提取指定章节新事实（带关系标注）并入剧情状态并生成章节摘要（每章写完后应调用）",
    category="提取",
)
def update_plot_state_tool(ctx: ToolContext, chapter_no: int) -> str:
    novel = _ensure_book(ctx)
    if not 1 <= chapter_no <= len(novel.chapters):
        raise ToolError(f"章节号超出范围（1-{len(novel.chapters)}）")
    chapter = novel.chapters[chapter_no - 1]
    text = "\n\n".join(s.content for s in chapter.scenes if s.content)
    if not text:
        raise ToolError(f"第{chapter_no}章还没有正文")
    memory = ctx.fresh_memory()
    state = memory.plot_state if memory is not None else novel.plot_state
    novel.plot_state, summary = update_memory(
        ctx.provider, text, chapter_no, state, chapter_title=chapter.title
    )
    if memory is not None:
        memory.plot_state = novel.plot_state
        if summary is not None:
            memory.chapter_summaries = [
                s for s in memory.chapter_summaries if s.chapter_no != chapter_no
            ] + [summary]
        ctx.save_memory()
    ctx.save()
    state = novel.plot_state
    return (
        f"剧情状态已更新：{len(state.characters)} 个角色，{len(state.events)} 个事件，"
        f"{len([s for s in state.setups if s.resolved_in is None])} 个未回收伏笔"
        + (f"；第{chapter_no}章摘要已生成" if summary is not None else "")
    )


def _plan_for(novel: Novel, idx: int) -> ChapterPlan:
    if idx <= len(novel.outline):
        return novel.outline[idx - 1]
    return ChapterPlan(title=f"第{idx}章", focus="")
