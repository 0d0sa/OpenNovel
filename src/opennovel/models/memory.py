"""Novel memory persistence schema (memory.json — 正文与记忆分离).

The per-novel memory holds what the consistency mechanisms need:
style_profile (语言风格一致性) + plot_state + chapter summaries (剧情连贯性).
It is persisted separately from `novel.json` (structure/text) so memory
updates never rewrite the whole book.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from opennovel.memory import PlotState, StyleProfile
from opennovel.memory.plot_state import ChapterSummary


class NovelMemory(BaseModel):
    """The complete per-novel memory, persisted at novels/<title>/memory.json."""

    version: int = Field(default=2, description="记忆格式版本")
    style_profile: StyleProfile = Field(default_factory=StyleProfile)
    plot_state: PlotState = Field(default_factory=PlotState)
    chapter_summaries: list[ChapterSummary] = Field(
        default_factory=list, description="每章结构化摘要（L1 索引）"
    )
