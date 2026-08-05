"""编写类工具：整章写作（复合）、单场景写作、连续写作（v2 base tool set）。"""

from __future__ import annotations

from opennovel.agent.orchestrator import write_one_chapter
from opennovel.agent.planning import ChapterPlan, plan_chapters, plan_scenes, write_scene
from opennovel.agent.tools import ToolContext, ToolError, ToolResult, tool
from opennovel.memory import (
    extract_style_profile,
    plot_state_brief,
    style_anchor_block,
)
from opennovel.models import Novel, Scene, SceneStatus


def _book(ctx: ToolContext) -> Novel:
    novel = ctx.fresh_novel()
    if novel is None:
        raise ToolError("还没有开始任何书，先用 append_plot 或 /new 创建")
    return novel


def _ensure_style(ctx: ToolContext, novel: Novel) -> None:
    if novel.style_profile and novel.style_profile.tone:
        return
    if ctx.on_stage:
        ctx.on_stage("提取风格锚点")
    novel.style_profile = extract_style_profile(ctx.provider, novel.plot, ctx.style_hint)


def _ensure_outline(ctx: ToolContext, novel: Novel) -> None:
    if novel.outline:
        return
    if ctx.on_stage:
        ctx.on_stage("规划全书大纲")
    novel.outline = plan_chapters(ctx.provider, novel.plot, ctx.settings.max_chapters)


@tool(
    "write_chapter",
    "写一章正文（复合：规划场景→逐场景写作→按设置检查→更新剧情状态→保存）；chapter_no=0 表示续写下一章",
    category="编写",
)
def write_chapter(ctx: ToolContext, chapter_no: int = 0) -> ToolResult:
    novel = _book(ctx)
    _ensure_style(ctx, novel)
    _ensure_outline(ctx, novel)
    idx = len(novel.chapters) + 1 if chapter_no <= 0 else chapter_no
    if idx <= 0 or idx > len(novel.outline):
        raise ToolError(f"第{idx}章超出大纲范围（共 {len(novel.outline)} 章，已写 {len(novel.chapters)} 章）；"
                        "如需更多章节请先 plan_outline 重新规划")
    plan = novel.outline[idx - 1]
    existing = novel.chapters[idx - 1] if idx <= len(novel.chapters) else None
    if existing is not None and any(s.content for s in existing.scenes):
        raise ToolError(f"第{idx}章已有正文；需要修改请用 rewrite_chapter 或 edit_chapter")
    scenes = existing.scenes if existing is not None and existing.scenes else None

    if ctx.on_token_start:
        ctx.on_token_start()
    try:
        chapter = write_one_chapter(
            ctx.provider,
            ctx.settings,
            novel,
            idx,
            plan,
            scenes=scenes,
            on_progress=ctx.on_progress,
            on_stage=ctx.on_stage,
            on_token=ctx.on_token,
        )
    finally:
        if ctx.on_token_end:
            ctx.on_token_end()

    if existing is not None:
        novel.chapters[idx - 1] = chapter
    else:
        novel.chapters.append(chapter)
    ctx.save()

    chars = sum(len(s.content) for s in chapter.scenes)
    style = f"{chapter.style_report.score}/5" if chapter.style_report else "未查"
    plot = f"{chapter.plot_report.score}/5" if chapter.plot_report else "未查"
    return ToolResult(
        summary=(
            f"第{idx}章《{chapter.title}》已完成：约 {chars} 字，风格检查 {style}，"
            f"剧情检查 {plot}，剧情状态已更新，已保存 novel.json。要点：{plan.focus}"
        )
    )


@tool(
    "write_scene",
    "写一个场景正文：scene_no=0 时写第一个未写的已规划场景，或按 summary 新建场景",
    category="编写",
)
def write_scene_tool(
    ctx: ToolContext, chapter_no: int, scene_no: int = 0, summary: str = ""
) -> ToolResult:
    novel = _book(ctx)
    if not 1 <= chapter_no <= len(novel.chapters):
        raise ToolError(f"章节号超出范围（1-{len(novel.chapters)}）；先调用 plan_scenes 创建章节")
    chapter = novel.chapters[chapter_no - 1]
    scene = None
    if scene_no > 0:
        if scene_no > len(chapter.scenes):
            raise ToolError(f"该章只有 {len(chapter.scenes)} 个场景")
        scene = chapter.scenes[scene_no - 1]
    else:
        scene = next((s for s in chapter.scenes if not s.content), None)
        if scene is None and summary.strip():
            scene = Scene(summary=summary.strip(), status=SceneStatus.PLANNED)
            chapter.scenes.append(scene)
    if scene is None:
        raise ToolError("该章没有待写的场景；请提供 summary 新建一个")

    anchor = style_anchor_block(novel.style_profile)
    brief = plot_state_brief(novel.plot_state)
    prev_tail = _prev_tail(chapter, scene)
    target = max(ctx.settings.chapter_target_chars // max(len(chapter.scenes), 1), 200)

    if ctx.on_token_start:
        ctx.on_token_start()
    try:
        text = write_scene(
            ctx.provider, scene, anchor, brief, prev_tail, target,
            stream_callback=ctx.on_token,
        )
    finally:
        if ctx.on_token_end:
            ctx.on_token_end()
    scene.content = text
    scene.status = SceneStatus.WRITTEN
    ctx.save()
    return ToolResult(
        summary=f"第{chapter_no}章场景「{scene.summary[:30]}」已写：{len(text)} 字，已保存"
    )


@tool("continue_writing", "从当前进度连续写作若干章", category="编写")
def continue_writing(ctx: ToolContext, chapters: int = 1) -> str:
    if chapters < 1 or chapters > 10:
        raise ToolError("一次最多连续写作 10 章")
    summaries = []
    for _ in range(chapters):
        result = write_chapter(ctx, 0)
        summaries.append(result.summary)
    return "\n".join(summaries)


def _prev_tail(chapter, scene) -> str:
    """Tail of the previously written scene in this chapter (for cohesion)."""
    for s in reversed(chapter.scenes):
        if s is scene:
            continue
        if s.content:
            return s.content[-200:]
    return ""
