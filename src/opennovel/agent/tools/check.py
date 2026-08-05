"""检查类工具：章节级风格与剧情一致性检查（v2 base tool set）。"""

from __future__ import annotations

from opennovel.agent.tools import ToolContext, ToolError, tool
from opennovel.memory import check_plot_consistency, check_style_deviation
from opennovel.models import Novel


def _book(ctx: ToolContext) -> Novel:
    novel = ctx.fresh_novel()
    if novel is None:
        raise ToolError("还没有开始任何书，先用 append_plot 或 /new 创建")
    return novel


def _chapter_text(novel: Novel, chapter_no: int):
    if not 1 <= chapter_no <= len(novel.chapters):
        raise ToolError(f"章节号超出范围（1-{len(novel.chapters)}）")
    chapter = novel.chapters[chapter_no - 1]
    text = "\n\n".join(s.content for s in chapter.scenes if s.content)
    if not text:
        raise ToolError(f"第{chapter_no}章还没有正文")
    return chapter, text


@tool("check_style", "检查指定章节的风格偏离度 0-5，并把报告写回章节", category="检查")
def check_style(ctx: ToolContext, chapter_no: int) -> str:
    novel = _book(ctx)
    chapter, text = _chapter_text(novel, chapter_no)
    report = check_style_deviation(ctx.provider, novel.style_profile, text)
    chapter.style_report = report
    ctx.save()
    lines = [f"第{chapter_no}章风格偏离度 {report.score}/5"]
    lines += [f"- {d}" for d in report.deviations[:5]]
    if report.suggestion:
        lines.append(f"建议：{report.suggestion}")
    return "\n".join(lines)


@tool("check_plot", "检查指定章节的剧情矛盾度 0-5，并把报告写回章节", category="检查")
def check_plot(ctx: ToolContext, chapter_no: int) -> str:
    novel = _book(ctx)
    chapter, text = _chapter_text(novel, chapter_no)
    report = check_plot_consistency(ctx.provider, novel.plot_state, text, chapter_no)
    chapter.plot_report = report
    ctx.save()
    lines = [f"第{chapter_no}章剧情矛盾度 {report.score}/5"]
    lines += [f"- {c}" for c in report.contradictions[:5]]
    if report.suggestion:
        lines.append(f"建议：{report.suggestion}")
    return "\n".join(lines)
