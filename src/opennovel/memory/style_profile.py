"""Style anchors for a single novel.

Purpose: capture the novel's voice once (tone, diction, sentence rhythm,
POV, tense) so every generated chapter/section is written against the same
style profile — the mechanism for 语言风格一致性.

MVP scope: a plain data container. How the profile is extracted, stored, and
injected into prompts is decided in the memory step of the MVP plan.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StyleProfile(BaseModel):
    """Per-novel style anchors written against by the agent."""

    tone: str = Field(default="", description="文风基调，如 冷峻/诙谐/诗意")
    pov: str = Field(default="", description="视角与人称，如 第三人称限知")
    tense: str = Field(default="", description="时态/叙事时间")
    diction: str = Field(default="", description="用语特点，如 短句/古白话/方言")
    sample_passage: str = Field(default="", description="风格样本段落，供 LLM 模仿")
