"""Per-novel memory/state that enforces the two core quality requirements.

- style_profile: language style consistency (语言风格一致性)
- plot_state:   plot coherence (剧情连贯性)
"""

from opennovel.memory.plot_state import CharacterRecord, EventRecord, PlotState, SetupRecord
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
    "PlotState",
    "SetupRecord",
    "StyleDeviation",
    "StyleProfile",
    "check_style_deviation",
    "extract_style_profile",
    "style_anchor_block",
]

