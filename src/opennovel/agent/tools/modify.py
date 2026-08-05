"""修改类工具：整章重写、定点修改、追加剧情（v2 base tool set）。"""

from __future__ import annotations

from opennovel.agent.planning import edit_chapter, rewrite_chapter
from opennovel.agent.tools import ToolContext, ToolError, ToolResult, tool
from opennovel.memory import plot_state_brief, style_anchor_block
from opennovel.models import Novel, Scene, SceneStatus


def _book(ctx: ToolContext) -> Novel:
    novel = ctx.fresh_novel()
    if novel is None:
        raise ToolError("还没有开始任何书，先用 append_plot 或 /new 创建")
    return novel


def _chapter_text(novel: Novel, chapter_no: int, need_content: bool = True) -> tuple:
    if not 1 <= chapter_no <= len(novel.chapters):
        raise ToolError(f"章节号超出范围（1-{len(novel.chapters)}）")
    chapter = novel.chapters[chapter_no - 1]
    text = "\n\n".join(s.content for s in chapter.scenes if s.content)
    if need_content and not text:
        raise ToolError(f"第{chapter_no}章还没有正文")
    return chapter, text


@tool("rewrite_chapter", "按用户指示（可选）与既有检查报告整章重写", category="修改")
def rewrite_chapter_tool(ctx: ToolContext, chapter_no: int, instructions: str = "") -> ToolResult:
    novel = _book(ctx)
    chapter, text = _chapter_text(novel, chapter_no)
    if ctx.on_stage:
        ctx.on_stage(f"重写第{chapter_no}章…")
    if ctx.on_token_start:
        ctx.on_token_start()
    try:
        new_text = rewrite_chapter(
            ctx.provider,
            text,
            chapter.style_report,
            chapter.plot_report,
            style_anchor_block(novel.style_profile),
            instructions=instructions,
            stream_callback=ctx.on_token,
        )
    finally:
        if ctx.on_token_end:
            ctx.on_token_end()
    chapter.scenes = [Scene(summary="重写稿", content=new_text, status=SceneStatus.WRITTEN)]
    chapter.style_report = None
    chapter.plot_report = None
    ctx.save()
    return ToolResult(
        summary=f"第{chapter_no}章已重写并保存（{len(new_text)} 字，检查报告已清空，可再调用 check_style/check_plot 复查）"
    )


@tool("edit_chapter", "按用户指示对章节做定点修改（只改动指定部分，其余原样保留）", category="修改")
def edit_chapter_tool(ctx: ToolContext, chapter_no: int, instructions: str) -> ToolResult:
    if not instructions.strip():
        raise ToolError("修改指示不能为空，例如：'把开头改成从雨夜开始'")
    novel = _book(ctx)
    chapter, text = _chapter_text(novel, chapter_no)
    if ctx.on_token_start:
        ctx.on_token_start()
    try:
        new_text = edit_chapter(
            ctx.provider,
            text,
            instructions,
            style_anchor_block(novel.style_profile),
            plot_brief=plot_state_brief(novel.plot_state),
            stream_callback=ctx.on_token,
        )
    finally:
        if ctx.on_token_end:
            ctx.on_token_end()
    chapter.scenes = [Scene(summary="修改稿", content=new_text, status=SceneStatus.WRITTEN)]
    chapter.style_report = None
    chapter.plot_report = None
    ctx.save()
    return ToolResult(
        summary=f"第{chapter_no}章已按指示修改并保存（{len(new_text)} 字；检查报告已清空）"
    )


@tool("append_plot", "把用户补充的剧情/设定/人物追加到当前书的剧情文本", category="修改")
def append_plot(ctx: ToolContext, text: str) -> str:
    if not ctx.title:
        raise ToolError("还没有开始任何书，先告诉我书名（如：新书叫《雾中城》，剧情是……）")
    novel = ctx.fresh_novel()
    if novel is not None and novel.plot:
        ctx.plot = novel.plot
    addition = text.strip()
    if not addition:
        raise ToolError("追加内容不能为空")
    if ctx.plot:
        ctx.plot = ctx.plot.rstrip() + "\n" + addition
    else:
        ctx.plot = addition
    if novel is None:
        novel = Novel(title=ctx.title, plot=ctx.plot)
        ctx.novel = novel
    else:
        novel.plot = ctx.plot
    ctx.save()
    return f"已追加到剧情（当前剧情共 {len(ctx.plot)} 字），已保存。"
