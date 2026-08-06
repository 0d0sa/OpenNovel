"""读取类工具：查看书、章节、剧情、风格与进度（v2 base tool set）。"""

from __future__ import annotations

from opennovel.agent.tools import ToolContext, ToolError, ToolResult, tool
from opennovel.memory import plot_state_brief, search_memory, style_anchor_block
from opennovel.models import Novel

READ_CHAPTER_CAP = 8000


def _book(ctx: ToolContext) -> Novel:
    if not ctx.title:
        raise ToolError("当前没有打开任何书，先告诉我书名与剧情")
    novel = ctx.fresh_novel() or ctx.novel
    if novel is None:
        raise ToolError(f"《{ctx.title}》还没有创建，先用 append_plot 或 /new 提供剧情")
    return novel


@tool("list_books", "列出所有已存在的书及进度", category="读取")
def list_books(ctx: ToolContext) -> str:
    base = ctx.settings.output_dir
    if not base.exists():
        return "还没有任何书。"
    lines = []
    for path in sorted(base.glob("*/novel.json")):
        try:
            novel = Novel.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        chars = sum(len(s.content) for ch in novel.chapters for s in ch.scenes)
        lines.append(f"- 《{novel.title}》：{len(novel.chapters)} 章，约 {chars} 字")
    return "\n".join(lines) or "还没有任何书。"


@tool("read_status", "查看当前书进度：章节数、各章字数与检查分、角色与伏笔统计", category="读取")
def read_status(ctx: ToolContext) -> str:
    novel = _book(ctx)
    lines = [f"《{novel.title}》进度："]
    outline = novel.outline or []
    lines.append(f"- 大纲 {len(outline)} 章，已写 {len(novel.chapters)} 章")
    for i, ch in enumerate(novel.chapters, 1):
        chars = sum(len(s.content) for s in ch.scenes)
        style = ch.style_report.score if ch.style_report else "-"
        plot = ch.plot_report.score if ch.plot_report else "-"
        lines.append(f"- 第{i}章 {ch.title}：{chars} 字，风格 {style}/5，剧情 {plot}/5")
    total = sum(len(s.content) for ch in novel.chapters for s in ch.scenes)
    lines.append(f"- 全书约 {total} 字，{len(novel.plot_state.characters)} 个角色，"
                 f"{len(novel.plot_state.events)} 个事件，"
                 f"{len([s for s in novel.plot_state.setups if s.resolved_in is None])} 个未回收伏笔")
    return "\n".join(lines)


@tool("read_novel", "查看当前书完整状态：大纲、各章标题/字数/检查分、剧情简报", category="读取")
def read_novel(ctx: ToolContext) -> str:
    novel = _book(ctx)
    lines = [f"《{novel.title}》"]
    if novel.outline:
        lines.append("大纲：")
        for i, p in enumerate(novel.outline, 1):
            lines.append(f"- 第{i}章 {p.title}：{p.focus}")
    lines.append(read_status(ctx))
    brief = plot_state_brief(novel.plot_state, max_chars=800)
    if brief:
        lines.append("剧情简报：")
        lines.append(brief)
    return "\n".join(lines)


@tool("read_chapter", "读取指定章节的标题与正文（最多 8000 字）", category="读取")
def read_chapter(ctx: ToolContext, chapter_no: int) -> str:
    novel = _book(ctx)
    if not 1 <= chapter_no <= len(novel.chapters):
        raise ToolError(f"章节号超出范围（1-{len(novel.chapters)}）")
    chapter = novel.chapters[chapter_no - 1]
    lines = [f"第{chapter_no}章 {chapter.title}"]
    if chapter.outline:
        lines.append(f"大纲：{chapter.outline}")
    text = "\n\n".join(s.content for s in chapter.scenes if s.content)
    if not text:
        lines.append("（本章还没有正文）")
    else:
        if len(text) > READ_CHAPTER_CAP:
            lines.append(text[:READ_CHAPTER_CAP] + "……（截断，本章较长）")
        else:
            lines.append(text)
    return "\n".join(lines)


@tool("read_plot", "查看当前书的原始剧情文本", category="读取")
def read_plot(ctx: ToolContext) -> str:
    novel = ctx.fresh_novel() or ctx.novel
    if novel is not None and novel.plot:
        ctx.plot = novel.plot
    if not ctx.plot:
        raise ToolError("还没有任何剧情，告诉我你想写什么故事")
    return ctx.plot


@tool("read_style", "查看当前书的风格档案（文风/视角/用语/样本段落）", category="读取")
def read_style(ctx: ToolContext) -> str:
    novel = ctx.fresh_novel() or ctx.novel
    profile = novel.style_profile if novel else None
    if profile is None or not profile.tone:
        return "（还没有风格档案，写作时会先提取）"
    lines = [
        f"- 文风基调：{profile.tone}",
        f"- 视角人称：{profile.pov}",
        f"- 叙事时态：{profile.tense}",
        f"- 用语特点：{profile.diction}",
    ]
    if profile.sample_passage:
        sample = profile.sample_passage[:300]
        lines.append(f"- 风格样本：{sample}")
    return "\n".join(lines)


@tool("read_anchor", "查看写作注入用的风格锚点块", category="读取")
def read_anchor(ctx: ToolContext) -> str:
    novel = ctx.fresh_novel() or ctx.novel
    profile = novel.style_profile if novel else None
    if profile is None or not profile.tone:
        return "（还没有风格档案）"
    return style_anchor_block(profile)


@tool(
    "search_memory",
    "在全书正文与章节摘要中按关键词检索相关片段（返回命中片段与章节号，供定位后 read_chapter 精读）",
    category="读取",
)
def search_memory_tool(ctx: ToolContext, query: str, limit: int = 5) -> str:
    novel = _book(ctx)
    memory = ctx.fresh_memory()
    snippets = search_memory(novel, memory, query, limit)
    if not snippets:
        return f"未找到与「{query}」相关的内容。"
    return "\n".join(snippets)


@tool("read_summary", "读取章节摘要：chapter_no=0 列出全部索引，否则读取单章摘要", category="读取")
def read_summary(ctx: ToolContext, chapter_no: int = 0) -> str:
    if not ctx.title:
        raise ToolError("当前没有打开任何书，先告诉我书名与剧情")
    memory = ctx.fresh_memory()
    if memory is None or not memory.chapter_summaries:
        return "（还没有章节摘要；写完章节后会自动生成）"
    if chapter_no == 0:
        lines = ["章节摘要索引："]
        for s in memory.chapter_summaries:
            hook = f"（hook：{s.hook}）" if s.hook else ""
            lines.append(f"- 第{s.chapter_no}章 {s.title}：{s.overview}{hook}")
        return "\n".join(lines)
    s = next((x for x in memory.chapter_summaries if x.chapter_no == chapter_no), None)
    if s is None:
        raise ToolError(f"还没有第{chapter_no}章的摘要")
    lines = [f"第{s.chapter_no}章《{s.title}》摘要："]
    if s.overview:
        lines.append(f"- 概述：{s.overview}")
    if s.events:
        lines.extend([f"- 事件：{e}" for e in s.events])
    if s.new_characters:
        lines.append(f"- 新角色：{'、'.join(s.new_characters)}")
    if s.new_setups:
        lines.extend([f"- 新伏笔：{x}" for x in s.new_setups])
    if s.resolved_setups:
        lines.extend([f"- 已回收伏笔：{x}" for x in s.resolved_setups])
    if s.key_facts:
        lines.extend([f"- 关键设定：{x}" for x in s.key_facts])
    if s.hook:
        lines.append(f"- 续写提示：{s.hook}")
    return "\n".join(lines)
