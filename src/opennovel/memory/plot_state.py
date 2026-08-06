"""Running plot state for a single novel.

Purpose: track characters, events, and open setups (伏笔) across chapters so
later chapters stay consistent with earlier ones — the mechanism for 剧情连贯性.

Operations (all go through the `llm/` abstraction, never touch SDKs):
- `update_memory`: per-chapter extraction with LLM-annotated relations
  (new/update/duplicate/extend/resolve) + chapter summary, merged
  deterministically in Python
- `plot_state_brief`: compressed brief injected into chapter prompts
- `check_plot_consistency`: chapter-level LLM check after each chapter
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from opennovel.llm import ChatMessage, CompletionRequest, Provider

UPDATE_MEMORY_SYSTEM = """你是剧情记录员。阅读章节原文，输出两部分：
A. 对既有剧情状态的关系化增量（对照【当前剧情状态】，只提交对后续剧情有影响的新内容）：
- new_characters：角色增量。relation=new 表示新角色；update_facts 表示补充既有角色的事实（target 用既有角色的 name 或描述标识）；update_role 表示修正既有角色定位。已确立的事实不要重复提交。
- events：事件增量。relation=new 表示新事件；duplicate_of 表示与既有事件重复（target 引用既有事件摘要，不要追加）；extends 表示补充既有事件细节（target 引用既有事件摘要）。
- new_setups：伏笔增量。relation=new 表示本章新埋伏笔；resolved 表示回收既有伏笔（target 引用既有伏笔描述）。
- resolved_setups：被回收伏笔的描述列表（与 new_setups 二选一，兼容旧格式）。
B. chapter_summary：本章结构化摘要。overview 一句话概括本章；events 列出关键事件；new_characters/resolved_setups/new_setups 与 A 一致；key_facts 列出影响后续的设定变化（身份/地点/时间线等）；hook 给出下一章需要衔接或待解决的要点。
不要提取与后续剧情无关的琐碎细节。"""

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


class CharacterUpdate(BaseModel):
    """Character delta annotated with its relation to existing state."""

    name: str = Field(description="角色名")
    role: str = Field(default="", description="身份/定位")
    facts: list[str] = Field(default_factory=list, description="已确立的关键事实")
    relation: Literal["new", "update_facts", "update_role"] = Field(
        default="new",
        description="new=新角色；update_facts=补充既有角色事实；update_role=修正既有角色定位",
    )
    target: str = Field(default="", description="update_* 时引用既有角色的 name 或描述，用于匹配")


class EventUpdate(BaseModel):
    """Event delta annotated with its relation to existing events."""

    summary: str = Field(description="事件概要")
    involved: list[str] = Field(default_factory=list, description="涉及角色名")
    relation: Literal["new", "duplicate_of", "extends"] = Field(
        default="new",
        description="new=新事件；duplicate_of=与既有事件重复（不追加）；extends=补充既有事件细节",
    )
    target: str = Field(default="", description="duplicate_of/extends 时引用既有事件摘要")


class SetupUpdate(BaseModel):
    """Setup delta annotated with its relation to existing setups."""

    description: str = Field(description="伏笔内容")
    relation: Literal["new", "resolved"] = Field(
        default="new", description="new=新伏笔；resolved=回收既有伏笔（target 引用）"
    )
    target: str = Field(default="", description="resolved 时引用既有伏笔描述")


class ChapterSummary(BaseModel):
    """Structured per-chapter summary (L1 memory): index + continuation hooks."""

    chapter_no: int = Field(default=0, description="章节号")
    title: str = Field(default="", description="章节标题")
    overview: str = Field(default="", description="本章发生了什么，一句话")
    events: list[str] = Field(default_factory=list, description="关键事件条目")
    new_characters: list[str] = Field(default_factory=list, description="本章新登场角色名")
    resolved_setups: list[str] = Field(default_factory=list, description="本章回收的伏笔简述")
    new_setups: list[str] = Field(default_factory=list, description="本章新埋的伏笔简述")
    hook: str = Field(default="", description="续写提示：下一章需衔接/待解决的要点")
    key_facts: list[str] = Field(default_factory=list, description="影响后续的设定变化")


class PlotStateUpdate(BaseModel):
    """Incremental update extracted from one chapter by the LLM (v2)."""

    new_characters: list[CharacterUpdate] = Field(default_factory=list)
    events: list[EventUpdate] = Field(default_factory=list)
    new_setups: list[SetupUpdate] = Field(default_factory=list)
    resolved_setups: list[str] = Field(default_factory=list, description="被回收伏笔的描述（按语义匹配）")
    chapter_summary: ChapterSummary | None = Field(default=None, description="本章结构化摘要")


class PlotConsistency(BaseModel):
    """Result of a chapter-level plot consistency check."""

    score: int = Field(ge=0, le=5, description="矛盾程度 0-5，0=无矛盾")
    contradictions: list[str] = Field(default_factory=list, description="矛盾点：引用原文+冲突说明")
    suggestion: str = Field(default="", description="整体修订建议，无矛盾可为空")


_PUNCT = re.compile(r"[\s，。！？、；：""''「」『』（）【】《》…·,.!?;:()—-]+")


def _normalize(text: str) -> str:
    return _PUNCT.sub("", text)


def semantic_match(query: str, candidates: list[str], threshold: float = 0.6) -> str | None:
    """Best normalized match of `query` against `candidates`.

    Pure function: exact/normalized substring counts as 1.0; otherwise
    character-overlap similarity; returns None below `threshold`.
    """
    q = _normalize(query)
    if not q or not candidates:
        return None
    best, best_score = None, 0.0
    for cand in candidates:
        n = _normalize(cand)
        if not n:
            continue
        if q == n or q in n or n in q:
            score = 1.0
        else:
            inter = len(set(q) & set(n))
            score = (2.0 * inter) / (len(q) + len(n))
        if score > best_score:
            best, best_score = cand, score
    return best if best_score >= threshold else None


def update_memory(
    provider: Provider,
    chapter_text: str,
    chapter_no: int,
    current: PlotState,
    chapter_title: str = "",
) -> tuple[PlotState, ChapterSummary | None]:
    """Extract annotated deltas + chapter summary from one chapter (LLM),
    then merge deterministically in Python. Returns (new state, summary)."""
    request = CompletionRequest(
        messages=[
            ChatMessage(role="system", content=UPDATE_MEMORY_SYSTEM),
            ChatMessage(role="user", content=f"【当前剧情状态】\n{plot_state_brief(current)}"),
            ChatMessage(role="user", content=f"【章节原文（第{chapter_no}章）】\n{chapter_text}"),
        ]
    )
    update = provider.complete_structured(request, PlotStateUpdate)
    state = _merge_update(current, update, chapter_no)
    summary = update.chapter_summary
    if summary is not None:
        summary = summary.model_copy(
            update={"chapter_no": chapter_no, "title": chapter_title or summary.title}
        )
    return state, summary


def update_plot_state(
    provider: Provider,
    chapter_text: str,
    chapter_no: int,
    current: PlotState,
) -> PlotState:
    """v1-compatible wrapper: extract deltas, ignore the summary."""
    state, _ = update_memory(provider, chapter_text, chapter_no, current)
    return state


def _merge_update(current: PlotState, update: PlotStateUpdate, chapter_no: int) -> PlotState:
    """Deterministic Python merge driven by the LLM's relation annotations.

    Conservative rules: unmatched resolutions never mark anything resolved;
    unmatched updates degrade to new entries.
    """
    characters = dict(current.characters)
    for cu in update.new_characters:
        existing = characters.get(cu.name)
        if existing is None:
            key = semantic_match(cu.target or cu.name, list(characters))
            existing = characters.get(key) if key else None
        if existing is None:
            characters[cu.name] = CharacterRecord(name=cu.name, role=cu.role, facts=list(cu.facts))
            continue
        updates: dict = {}
        if cu.facts:
            new_facts = [f for f in cu.facts if f not in existing.facts]
            updates["facts"] = existing.facts + new_facts
        if cu.relation == "update_role" and cu.role:
            updates["role"] = cu.role
        if updates:
            characters[existing.name] = existing.model_copy(update=updates)

    events = list(current.events)
    summaries = [e.summary for e in events]
    for ev in update.events:
        if ev.relation in ("duplicate_of", "extends"):
            target = semantic_match(ev.target or ev.summary, summaries)
            if target is not None:
                if ev.relation == "duplicate_of":
                    continue  # duplicate: drop
                matched = next(e for e in events if e.summary == target)
                new_involved = [i for i in ev.involved if i not in matched.involved]
                if new_involved:
                    idx = events.index(matched)
                    events[idx] = matched.model_copy(
                        update={"involved": matched.involved + new_involved}
                    )
                continue
        events.append(
            EventRecord(summary=ev.summary, chapter=chapter_no, involved=list(ev.involved))
        )

    setups = list(current.setups)
    open_descriptions = [s.description for s in setups if s.resolved_in is None]
    for su in update.new_setups:
        if su.relation == "resolved":
            target = semantic_match(su.target or su.description, open_descriptions)
            if target is not None:
                idx = next(
                    i
                    for i, s in enumerate(setups)
                    if s.description == target and s.resolved_in is None
                )
                setups[idx] = setups[idx].model_copy(update={"resolved_in": chapter_no})
                open_descriptions = [s.description for s in setups if s.resolved_in is None]
                continue
            # unmatched resolution degrades to a new setup (conservative)
        setups.append(SetupRecord(description=su.description, chapter=chapter_no))

    resolved = {s.strip() for s in update.resolved_setups if s.strip()}
    if resolved:
        open_descriptions = [s.description for s in setups if s.resolved_in is None]
        for desc in resolved:
            target = semantic_match(desc, open_descriptions)
            if target is None:
                continue
            idx = next(
                i
                for i, s in enumerate(setups)
                if s.description == target and s.resolved_in is None
            )
            setups[idx] = setups[idx].model_copy(update={"resolved_in": chapter_no})

    return current.model_copy(
        update={"characters": characters, "events": events, "setups": setups}
    )


def plot_state_brief(state: PlotState, max_chars: int = 500, include_setups: bool = True) -> str:
    """Compress PlotState into a short brief injected into chapter prompts.

    Unresolved setups come first (priority); characters/events follow.
    When `include_setups` is False the caller injects setups separately and
    guarantees they are never truncated.
    """
    lines: list[str] = []
    if include_setups:
        open_setups = [s for s in state.setups if s.resolved_in is None]
        if open_setups:
            lines.append("待回收伏笔：")
            for setup in open_setups:
                lines.append(f"- {setup.description}")
    if state.characters:
        lines.append("角色：")
        for char in state.characters.values():
            facts = "；".join(char.facts)
            lines.append(f"- {char.name}（{char.role}）{'：' + facts if facts else ''}")
    if state.events:
        lines.append("已发生事件：")
        for event in state.events:
            lines.append(f"- 第{event.chapter}章 {event.summary}")
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
