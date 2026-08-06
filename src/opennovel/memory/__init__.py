"""Per-novel memory/state that enforces the two core quality requirements.

- style_profile: language style consistency (语言风格一致性)
- plot_state:   plot coherence (剧情连贯性) — v2: relation-annotated merge
  + per-chapter summaries + zero-dependency full-text retrieval
"""

from opennovel.memory.plot_state import (
    ChapterSummary,
    CharacterRecord,
    CharacterUpdate,
    EventRecord,
    EventUpdate,
    PlotConsistency,
    PlotState,
    PlotStateUpdate,
    SetupRecord,
    SetupUpdate,
    check_plot_consistency,
    plot_state_brief,
    semantic_match,
    update_memory,
    update_plot_state,
)
from opennovel.memory.style_profile import (
    StyleDeviation,
    StyleProfile,
    check_style_deviation,
    extract_style_profile,
    style_anchor_block,
)
from opennovel.memory.retrieval import search_memory, split_sentences
from opennovel.memory.summary import build_writing_brief

__all__ = [
    "ChapterSummary",
    "CharacterRecord",
    "CharacterUpdate",
    "EventRecord",
    "EventUpdate",
    "PlotConsistency",
    "PlotState",
    "PlotStateUpdate",
    "SetupRecord",
    "SetupUpdate",
    "StyleDeviation",
    "StyleProfile",
    "build_writing_brief",
    "check_plot_consistency",
    "check_style_deviation",
    "extract_style_profile",
    "plot_state_brief",
    "search_memory",
    "semantic_match",
    "split_sentences",
    "style_anchor_block",
    "update_memory",
    "update_plot_state",
]

