"""Per-novel memory/state that enforces the two core quality requirements.

- style_profile: language style consistency (语言风格一致性)
- plot_state:   plot coherence (剧情连贯性)
"""

from opennovel.memory.plot_state import (
    CharacterRecord,
    EventRecord,
    PlotConsistency,
    PlotState,
    PlotStateUpdate,
    SetupRecord,
    check_plot_consistency,
    plot_state_brief,
    update_plot_state,
)
from opennovel.memory.style_profile import (
    StyleDeviation,
    StyleProfile,
    check_style_deviation,
    extract_style_profile,
    style_anchor_block,
)

__all__ = [
    "CharacterRecord",
    "EventRecord",
    "PlotConsistency",
    "PlotState",
    "PlotStateUpdate",
    "SetupRecord",
    "StyleDeviation",
    "StyleProfile",
    "check_plot_consistency",
    "check_style_deviation",
    "extract_style_profile",
    "plot_state_brief",
    "style_anchor_block",
    "update_plot_state",
]

