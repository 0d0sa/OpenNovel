"""Agent layer (v2): intent self-determination + base tool set.

- `loop.py`: run_turn — chat or chained tool calls (the v2 entry point)
- `tools/`: base tools (读取/提取/编写/修改/保存/检查) registered via @tool
- `planning.py`: per-step LLM prompts (outline / scenes / writing / rewrite)
- `orchestrator.py`: batch pipeline (`write_novel`) + single-chapter unit
"""

from opennovel.agent.context import build_background, build_history
from opennovel.agent.loop import AgentTurn, MAX_TOOL_STEPS, ToolCall, run_turn
from opennovel.agent.planning import (
    ChapterPlanList,
    ScenePlanList,
    edit_chapter,
    plan_chapters,
    plan_scenes,
    rewrite_chapter,
    write_scene,
)
from opennovel.agent.orchestrator import chapter_text, export_novel_text, write_novel
from opennovel.agent.tools import (
    TOOLS,
    ToolContext,
    ToolError,
    ToolResult,
    ToolSpec,
    run_tool,
    tool,
    tool_catalog,
)

__all__ = [
    "AgentTurn",
    "ChapterPlanList",
    "MAX_TOOL_STEPS",
    "ScenePlanList",
    "TOOLS",
    "ToolCall",
    "ToolContext",
    "ToolError",
    "ToolResult",
    "ToolSpec",
    "build_background",
    "build_history",
    "chapter_text",
    "edit_chapter",
    "export_novel_text",
    "plan_chapters",
    "plan_scenes",
    "rewrite_chapter",
    "run_tool",
    "run_turn",
    "tool",
    "tool_catalog",
    "write_novel",
    "write_scene",
]
