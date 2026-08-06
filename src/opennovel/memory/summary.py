"""写前简报校验：写作/修改工具注入内容的组装（记忆 v2）。

Builds the writing-time injection from memory: style anchor + complete open
setups (never truncated) + priority-compressed brief + recent chapter
summaries with continuation hooks.
"""

from __future__ import annotations

from opennovel.memory.plot_state import plot_state_brief
from opennovel.memory.style_profile import style_anchor_block


def build_writing_brief(memory, novel, chapter_no: int = 0, max_brief_chars: int = 600) -> str:
    """Assemble the injection block for writing/editing prompts.

    `memory` (NovelMemory | None) and `novel` (Novel) are duck-typed; when
    memory is missing the novel's own fields are used (v1 compat).
    """
    profile = memory.style_profile if memory is not None else novel.style_profile
    state = memory.plot_state if memory is not None else novel.plot_state
    lines: list[str] = []
    if profile and profile.tone:
        lines.append(style_anchor_block(profile))

    open_setups = [s for s in state.setups if s.resolved_in is None]
    if open_setups:
        lines.append("【待回收伏笔（写作时必须遵守，不得提前揭露）】")
        for s in open_setups:
            lines.append(f"- {s.description}")

    brief = plot_state_brief(state, max_chars=max_brief_chars, include_setups=False)
    if brief:
        lines.append("【剧情简报】")
        lines.append(brief)

    summaries = memory.chapter_summaries if memory is not None else []
    if summaries:
        related = [
            s for s in summaries if chapter_no <= 0 or s.chapter_no < chapter_no
        ][-2:]
        if related:
            lines.append("【最近章节摘要】")
            for s in related:
                lines.append(f"- 第{s.chapter_no}章 {s.title}：{s.overview}")
                if s.hook:
                    lines.append(f"  续写提示：{s.hook}")
    return "\n".join(lines)
