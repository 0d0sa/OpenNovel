"""Running plot state for a single novel.

Purpose: track characters, events, and open setups (伏笔) across chapters so
later chapters stay consistent with earlier ones — the mechanism for 剧情连贯性.

Three operations (all go through the `llm/` abstraction, never touch SDKs):
- `update_plot_state`: per-chapter incremental extraction + deterministic merge
- `plot_state_brief`: compressed brief injected into each chapter prompt
- `check_plot_consistency`: chapter-level LLM check after each chapter
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from opennovel.llm import ChatMessage, CompletionRequest, Provider

UPDATE_SYSTEM = """你是剧情记录员。阅读章节原文，把对后续剧情有影响的新内容提取为结构化增量：
- new_characters：新出现的角色（name 唯一，role 身份定位，facts 已确立的关键事实/经历，各不超过一句话）
- events：本章发生的重大事件（summary 一句概括，involved 涉及角色名）
- new_setups：本章新埋设的伏笔（描述当前看起来不重要、但可能后续回收的情节细节）
- resolved_setups：本章被回收（兑现/解释）的既有伏笔描述
不要提取与后续剧情无关的琐碎细节；已在既有状态中的角色/事件不要重复提交。"""

CHECK_SYSTEM = """你是严格的剧情校对。对照【既有剧情状态】和【新章节原文】，
找出与既有事实冲突之处（人物设定/生死/关系、时间线顺序、已发生事件被推翻等）。
- score：矛盾程度 0-5（0=无矛盾，5=严重矛盾）
- contradictions：矛盾点列表，每项引用新章节原文并说明与哪条既有事实冲突
- suggestion：整体修订建议，无矛盾则留空"""


class CharacterRecord(BaseModel):
    """A character as tracked in plot state (referenced by name)."""

    name: str = Field(description="角色名")
    role: str = Field(default="", description="身份/定位")
    facts: list[str] = Field(default_factory=list, description="已确立的事实/经历")


class EventRecord(BaseModel):
    """A plot event as tracked in plot state."""

    summary: str = Field(description="事件概要")
    chapter: int | None = Field(default=None, description="发生在第几章")
    involved: list[str] = Field(default_factory=list, description="涉及角色名")


class SetupRecord(BaseModel):
    """An open setup (伏笔) that must eventually pay off."""

    description: str = Field(description="伏笔内容")
    chapter: int | None = Field(default=None, description="埋设章节")
    resolved_in: int | None = Field(default=None, description="回收章节，未回收为 None")


class PlotState(BaseModel):
    """Per-novel running state: characters, events, open setups."""

    characters: dict[str, CharacterRecord] = Field(default_factory=dict)
    events: list[EventRecord] = Field(default_factory=list)
    setups: list[SetupRecord] = Field(default_factory=list)


class PlotStateUpdate(BaseModel):
    """Incremental update extracted from one chapter by the LLM."""

    new_characters: list[CharacterRecord] = Field(default_factory=list)
    events: list[EventRecord] = Field(default_factory=list)
    new_setups: list[SetupRecord] = Field(default_factory=list)
    resolved_setups: list[str] = Field(default_factory=list, description="被回收伏笔的描述")


class PlotConsistency(BaseModel):
    """Result of a chapter-level plot consistency check."""

    score: int = Field(ge=0, le=5, description="矛盾程度 0-5，0=无矛盾")
    contradictions: list[str] = Field(default_factory=list, description="矛盾点：引用原文+冲突说明")
    suggestion: str = Field(default="", description="整体修订建议，无矛盾可为空")


def update_plot_state(
    provider: Provider,
    chapter_text: str,
    chapter_no: int,
    current: PlotState,
) -> PlotState:
    """Extract new facts from a chapter (LLM) and merge them deterministically.

    The merge is done in Python (no LLM), so it is testable and traceable:
    - new characters are added by name; existing ones are never overwritten
    - events/setups are appended (chapter = current chapter)
    - resolved setups are marked with `resolved_in` = current chapter
    """
    request = CompletionRequest(
        messages=[
            ChatMessage(role="system", content=UPDATE_SYSTEM),
            ChatMessage(role="user", content=f"【当前剧情状态】\n{plot_state_brief(current)}"),
            ChatMessage(role="user", content=f"【章节原文（第{chapter_no}章）】\n{chapter_text}"),
        ]
    )
    update = provider.complete_structured(request, PlotStateUpdate)
    return _merge_update(current, update, chapter_no)


def _merge_update(current: PlotState, update: PlotStateUpdate, chapter_no: int) -> PlotState:
    characters = dict(current.characters)
    for char in update.new_characters:
        existing = characters.get(char.name)
        if existing is None:
            characters[char.name] = char
        elif char.facts:
            new_facts = [f for f in char.facts if f not in existing.facts]
            existing = existing.model_copy(update={"facts": existing.facts + new_facts})
            characters[char.name] = existing

    events = list(current.events)
    for event in update.events:
        event = event.model_copy(
            update={"chapter": chapter_no if event.chapter is None else event.chapter}
        )
        events.append(event)

    setups = list(current.setups)
    for setup in update.new_setups:
        setup = setup.model_copy(update={"chapter": setup.chapter or chapter_no})
        setups.append(setup)

    resolved = {s.strip() for s in update.resolved_setups if s.strip()}
    if resolved:
        setups = [
            s.model_copy(update={"resolved_in": chapter_no})
            if s.resolved_in is None and s.description in resolved
            else s
            for s in setups
        ]

    return current.model_copy(
        update={"characters": characters, "events": events, "setups": setups}
    )


def plot_state_brief(state: PlotState, max_chars: int = 500) -> str:
    """Compress PlotState into a short brief injected into chapter prompts.

    Unresolved setups are always included (explicitly flagged), so foreshadowing
    is never lost between chapters.
    """
    lines: list[str] = []
    if state.characters:
        lines.append("角色：")
        for char in state.characters.values():
            facts = "；".join(char.facts)
            lines.append(f"- {char.name}（{char.role}）{'：' + facts if facts else ''}")
    if state.events:
        lines.append("已发生事件：")
        for event in state.events:
            lines.append(f"- 第{event.chapter}章 {event.summary}")
    open_setups = [s for s in state.setups if s.resolved_in is None]
    if open_setups:
        lines.append("待回收伏笔：")
        for setup in open_setups:
            lines.append(f"- {setup.description}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "……（截断）"
    return text


def check_plot_consistency(
    provider: Provider,
    state: PlotState,
    chapter_text: str,
    chapter_no: int,
) -> PlotConsistency:
    """Chapter-level check: compare new text against established facts."""
    request = CompletionRequest(
        messages=[
            ChatMessage(role="system", content=CHECK_SYSTEM),
            ChatMessage(role="user", content=f"【既有剧情状态】\n{plot_state_brief(state)}"),
            ChatMessage(role="user", content=f"【新章节原文（第{chapter_no}章）】\n{chapter_text}"),
        ]
    )
    return provider.complete_structured(request, PlotConsistency)
