"""保存类工具：持久化 novel.json 与导出 novel.txt（v2 base tool set）。"""

from __future__ import annotations

from opennovel.agent.orchestrator import export_novel_text
from opennovel.agent.tools import ToolContext, ToolError, tool


@tool("save", "强制把当前书保存到 novel.json", category="保存")
def save(ctx: ToolContext) -> str:
    path = ctx.save()
    return f"已保存：{path}"


@tool("export_txt", "把全书导出为纯文本 novel.txt（供阅读）", category="保存")
def export_txt(ctx: ToolContext) -> str:
    if ctx.novel is None or not ctx.novel.chapters:
        raise ToolError("还没有任何章节可导出")
    path = export_novel_text(ctx.novel, ctx.settings.output_dir / ctx.novel.title / "novel.txt")
    return f"已导出：{path}"
