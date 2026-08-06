"""Background context and conversation history assembly for the agent loop.

The two non-negotiable quality requirements (语言风格一致性 / 剧情连贯性)
are enforced here at the context level: style anchor + complete open setups
+ priority-compressed brief + chapter summary index are injected every turn.
"""

from __future__ import annotations

from opennovel.agent.tools import ToolContext, tool_catalog
from opennovel.llm import ChatMessage
from opennovel.memory import plot_state_brief, style_anchor_block

HISTORY_WINDOW = 30


def build_background(ctx: ToolContext) -> str:
    """Assemble the per-turn background section appended to the system prompt."""
    lines = ["", "【当前作品背景】"]
    if not ctx.title:
        lines.append("- 还没有开始任何书。用户提出新故事时，先确认书名与剧情，再创建。")
    else:
        novel = ctx.fresh_novel()
        memory = ctx.fresh_memory()
        lines.append(f"- 书名：{ctx.title}")
        if novel is None:
            lines.append("- 书已创建但尚无内容（剧情保存在剧情文本中）")
        else:
            profile = memory.style_profile if memory is not None else novel.style_profile
            if profile and profile.tone:
                lines.append("- 风格档案（写作必须遵守）：")
                lines.append(style_anchor_block(profile))
            state = memory.plot_state if memory is not None else novel.plot_state
            open_setups = [s for s in state.setups if s.resolved_in is None]
            if open_setups:
                lines.append("- 待回收伏笔（完整，不得提前揭露）：")
                for setup in open_setups:
                    lines.append(f"  - {setup.description}")
            brief = plot_state_brief(state, max_chars=600, include_setups=False)
            if brief:
                lines.append("- 剧情简报：")
                lines.append(brief)
            summaries = memory.chapter_summaries if memory is not None else []
            if summaries:
                lines.append("- 章节摘要索引（咨询/续写时据此选择 read_chapter 精读）：")
                for s in summaries:
                    lines.append(f"  第{s.chapter_no}章 {s.title}：{s.overview}")
            lines.append("- 章节进度：")
            if novel.chapters:
                for i, ch in enumerate(novel.chapters, 1):
                    chars = sum(len(s.content) for s in ch.scenes)
                    style = ch.style_report.score if ch.style_report else "-"
                    plot = ch.plot_report.score if ch.plot_report else "-"
                    lines.append(f"  第{i}章 {ch.title}（{chars}字，风格{style}/5 剧情{plot}/5）")
            else:
                lines.append("  （尚未写任何章节）")
            if novel.outline:
                lines.append(f"- 大纲共 {len(novel.outline)} 章：")
                for i, p in enumerate(novel.outline, 1):
                    lines.append(f"  第{i}章 {p.title}：{p.focus}")
    lines.append("【可用工具】")
    lines.append(tool_catalog())
    return "\n".join(lines)


def build_history(
    messages: list[tuple[str, str]], window: int = HISTORY_WINDOW
) -> list[ChatMessage]:
    """Convert persisted chat messages into the prompt history window.

    Only user/assistant turns are fed back (UI system entries are stage
    noise); the most recent `window` messages are kept.
    """
    out: list[ChatMessage] = []
    for role, text in messages:
        if role not in ("user", "assistant") or not text:
            continue
        out.append(ChatMessage(role=role, content=text))
    return out[-window:]
