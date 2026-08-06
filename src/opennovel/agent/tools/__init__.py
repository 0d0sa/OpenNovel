"""Base tool layer for the v2 agent loop.

Tools are plain Python functions registered with `@tool`. Each tool gets a
`ToolContext` plus typed parameters; the registry derives a JSON schema from
the signature and executes calls. Nothing here touches LLM SDKs or the UI —
tools compose the `memory/`, `models/` and `planning.py` primitives.
"""

from __future__ import annotations

import inspect
import typing
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import create_model

from opennovel.config import Settings
from opennovel.llm import Provider
from opennovel.models import Novel, NovelMemory


class ToolError(RuntimeError):
    """Tool failure surfaced to the model as a tool result message."""


@dataclass
class ToolResult:
    """Outcome of one tool execution."""

    summary: str = ""
    visible: bool = True


@dataclass
class ToolContext:
    """State and callbacks handed to every tool (built by the UI per turn)."""

    provider: Provider
    settings: Settings
    title: str = ""
    plot: str = ""
    style_hint: str = ""
    novel: Novel | None = None
    memory: NovelMemory | None = None
    on_progress: object | None = None
    on_stage: object | None = None
    on_token_start: object | None = None
    on_token: object | None = None
    on_token_end: object | None = None

    def novel_path(self) -> Path:
        return self.settings.output_dir / self.title / "novel.json"

    def fresh_novel(self) -> Novel | None:
        """Get the current novel for a tool run (optimistic concurrency):
        reload from disk when it exists; otherwise keep the in-memory novel,
        or auto-create a blank book when the title is known. Returns None
        only when no title is set at all."""
        if not self.title:
            return None
        from opennovel.models import load_novel

        path = self.novel_path()
        if path.exists():
            self.novel = load_novel(path)
        elif self.novel is None:
            self.novel = Novel(title=self.title, plot=self.plot)
        return self.novel

    def save(self) -> Path:
        """Persist the current novel (creates parents). Raises when no book."""
        from opennovel.models import save_novel

        if self.novel is None:
            raise ToolError("还没有开始任何书，先 /new 创建或直接告诉我书名与剧情")
        return save_novel(self.novel, self.novel_path())

    def memory_path(self) -> Path:
        return self.settings.output_dir / self.title / "memory.json"

    def fresh_memory(self) -> NovelMemory | None:
        """Get the per-novel memory (reload from disk when present). Creates
        it on first access, migrating style/plot state out of novel.json.

        Never replaces `self.novel`: the migration reads the already-loaded
        novel (or loads one only when none is held), so tools that fetched a
        novel earlier keep the object they will mutate and save."""
        if not self.title:
            return None
        from opennovel.models import load_memory, save_memory

        memory = load_memory(self.title, self.settings.output_dir)
        if memory is None:
            novel = self.novel
            if novel is None:
                novel = self.fresh_novel()
            memory = NovelMemory()
            if novel is not None:
                memory.style_profile = novel.style_profile
                memory.plot_state = novel.plot_state
            save_memory(memory, self.memory_path())
        self.memory = memory
        return memory

    def save_memory(self) -> Path:
        """Persist the per-novel memory. Raises when none was loaded."""
        from opennovel.models import save_memory

        if self.memory is None:
            raise ToolError("记忆尚未初始化（fresh_memory 后才能保存）")
        return save_memory(self.memory, self.memory_path())


@dataclass
class ToolSpec:
    name: str
    description: str
    category: str
    handler: object
    schema: dict


TOOLS: dict[str, ToolSpec] = {}


def tool(name: str, description: str, category: str = ""):
    """Register a tool. The handler's first parameter must be `ctx:
    ToolContext`; the rest become typed tool parameters (JSON schema is
    derived from annotations and defaults)."""

    def deco(fn):
        TOOLS[name] = ToolSpec(
            name=name,
            description=description,
            category=category,
            handler=fn,
            schema=_param_schema(fn),
        )
        return fn

    return deco


def run_tool(name: str, arguments: dict, ctx: ToolContext) -> ToolResult:
    """Execute a tool by name with validated arguments."""
    spec = TOOLS.get(name)
    if spec is None:
        raise ToolError(f"未知工具：{name}")
    try:
        result = spec.handler(ctx, **arguments)
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"工具 {name} 执行失败：{exc}") from exc
    if isinstance(result, ToolResult):
        return result
    return ToolResult(summary=str(result))


def tool_catalog() -> str:
    """Human-readable tool list injected into the agent system prompt."""
    lines = []
    for spec in sorted(TOOLS.values(), key=lambda s: (s.category, s.name)):
        props = spec.schema["properties"]
        args = ", ".join(f"{n}: {_type_str(p)}" for n, p in props.items())
        lines.append(f"- {spec.name}：{spec.description}（参数：{args or '无'}）")
    return "\n".join(lines)


def _param_schema(fn) -> dict:
    hints = typing.get_type_hints(fn)
    signature = inspect.signature(fn)
    fields: dict[str, object] = {}
    for pname, param in signature.parameters.items():
        if pname == "ctx":
            continue
        typ = hints.get(pname, str)
        default = param.default
        if default is inspect.Parameter.empty:
            fields[pname] = (typ, ...)
        else:
            fields[pname] = (typ, default)
    model = create_model(f"{fn.__name__}Params", **fields)
    schema = model.model_json_schema()
    return {
        "properties": schema.get("properties", {}),
        "required": schema.get("required", []),
    }


def _type_str(prop: dict) -> str:
    t = prop.get("type")
    if t == "integer":
        return "int"
    if t == "number":
        return "float"
    if t == "boolean":
        return "bool"
    if t == "array":
        return "list"
    if t is None:
        for alt in prop.get("anyOf", []):
            if alt.get("type") != "null":
                return _type_str(alt) + "|None"
        return "?"
    return "str"


# Import tool modules so their @tool registrations run (after the decorator
# and registry above are defined).
from opennovel.agent.tools import check, extract, modify, persist, read, write  # noqa: E402,F401
