"""Data models describing a novel's structure.

`Novel` is the aggregate root: one Novel object is one book, and it holds the
two consistency mechanisms (style_profile / plot_state) together with the
chapter/scene tree — the unit of 语言风格一致性 and 剧情连贯性.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from opennovel.memory import PlotConsistency, PlotState, StyleDeviation, StyleProfile


class SceneStatus(StrEnum):
    PLANNED = "planned"
    WRITTEN = "written"


class Scene(BaseModel):
    """A scene: outline first, content filled in at writing time."""

    summary: str = Field(description="场景大纲")
    content: str = Field(default="", description="正文，写作后填充")
    status: SceneStatus = SceneStatus.PLANNED


class ChapterPlan(BaseModel):
    """One chapter in the book outline (persisted on Novel.outline)."""

    title: str = Field(description="章节标题")
    focus: str = Field(default="", description="本章核心冲突或进展，一句话")
    scene_count: int = Field(default=3, ge=1, le=6, description="本章场景数，建议 2-4")


class Chapter(BaseModel):
    """A chapter: a planning unit and a container of scenes."""

    title: str = Field(default="", description="章节标题")
    outline: str = Field(default="", description="章节大纲")
    scenes: list[Scene] = Field(default_factory=list)
    style_report: StyleDeviation | None = Field(default=None, description="章节风格检查报告")
    plot_report: PlotConsistency | None = Field(default=None, description="章节剧情检查报告")


class Character(BaseModel):
    """A character in the novel (used by plots/outlines; tracked in PlotState)."""

    name: str = Field(description="角色名")
    role: str = Field(default="", description="身份/定位")
    details: str = Field(default="", description="关键背景/设定")


class Novel(BaseModel):
    """Aggregate root: one object = one book, holding style + plot state."""

    title: str = Field(description="书名")
    plot: str = Field(default="", description="用户提供的剧情（原始文本）")
    style_profile: StyleProfile = Field(default_factory=StyleProfile)
    plot_state: PlotState = Field(default_factory=PlotState)
    outline: list[ChapterPlan] = Field(default_factory=list, description="全书章节大纲（持久化，供续写/工具使用）")
    chapters: list[Chapter] = Field(default_factory=list)
