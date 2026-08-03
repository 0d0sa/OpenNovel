"""Agent orchestration (MVP step 5): plot (剧情) -> chapters.

`write_novel` in `orchestrator.py` runs the full pipeline; `planning.py`
holds the per-step LLM prompts (outline / scenes / writing / rewrite).
"""

from opennovel.agent.intent import Intent, IntentKind, classify_intent
from opennovel.agent.planning import (
    ChapterPlan,
    ChapterPlanList,
    ScenePlanList,
    plan_chapters,
    plan_scenes,
    rewrite_chapter,
    write_scene,
)
from opennovel.agent.orchestrator import chapter_text, export_novel_text, write_novel

__all__ = [
    "ChapterPlan",
    "ChapterPlanList",
    "Intent",
    "IntentKind",
    "ScenePlanList",
    "chapter_text",
    "classify_intent",
    "export_novel_text",
    "plan_chapters",
    "plan_scenes",
    "rewrite_chapter",
    "write_novel",
    "write_scene",
]
