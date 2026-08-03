"""Running plot state for a single novel.

Purpose: track characters, events, and open setups (伏笔) across chapters so
later chapters stay consistent with earlier ones — the mechanism for 剧情连贯性.

MVP scope: plain data containers. Update/consistency-check logic is decided in
the memory step of the MVP plan.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


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
