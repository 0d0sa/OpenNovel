"""Per-novel memory/state that enforces the two core quality requirements.

- style_profile: language style consistency (语言风格一致性)
- plot_state:   plot coherence (剧情连贯性)
"""

from opennovel.memory.plot_state import CharacterRecord, EventRecord, PlotState, SetupRecord
from opennovel.memory.style_profile import StyleProfile

__all__ = [
    "CharacterRecord",
    "EventRecord",
    "PlotState",
    "SetupRecord",
    "StyleProfile",
]

