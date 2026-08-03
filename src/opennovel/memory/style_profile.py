"""Style anchors for a single novel.

Purpose: capture the novel's voice once (tone, diction, sentence rhythm,
POV, tense) so every generated chapter/section is written against the same
style profile — the mechanism for 语言风格一致性.

Three operations (all go through the `llm/` abstraction, never touch SDKs):
- `extract_style_profile`: one-time upfront extraction before writing
- `style_anchor_block`: build the system prompt anchor for each chapter
- `check_style_deviation`: chapter-level LLM check after each chapter
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from opennovel.llm import ChatMessage, CompletionRequest, Provider

EXTRACT_SYSTEM = """你是小说风格分析器。根据用户提供的剧情（和可选风格要求），推断并固化一种统一的小说文风：
- tone：文风基调，如 冷峻/诙谐/诗意/纪实
- pov：视角与人称，如 第三人称限知/第一人称
- tense：叙事时态/时间感
- diction：用语特点，如 短句/长句铺陈/古白话/口语化/大量比喻

最后用你设定的文风写一段 100-200 字的原创风格样本段落（sample_passage），
体现以上所有特征，作为全书写作的模仿标杆。不要写剧情内容，专注风格本身。"""

CHECK_SYSTEM = """你是严格的文风校对。对照给定的作品风格锚点和章节原文，
找出明显的风格偏离（语气、视角、用语、节奏与锚点不一致之处），忽略可接受的细微差异。
- score：风格偏离度 0-5（0=完全一致，5=严重偏离）
- deviations：偏离点列表，每项引用原文并说明问题
- suggestion：整体改写建议，无偏离则留空"""


class StyleProfile(BaseModel):
    """Per-novel style anchors written against by the agent."""

    tone: str = Field(default="", description="文风基调，如 冷峻/诙谐/诗意")
    pov: str = Field(default="", description="视角与人称，如 第三人称限知")
    tense: str = Field(default="", description="时态/叙事时间")
    diction: str = Field(default="", description="用语特点，如 短句/古白话/方言")
    sample_passage: str = Field(default="", description="风格样本段落，供 LLM 模仿")


class StyleDeviation(BaseModel):
    """Result of a chapter-level style consistency check."""

    score: int = Field(ge=0, le=5, description="风格偏离度 0-5，0=完全一致")
    deviations: list[str] = Field(default_factory=list, description="偏离点：引用原文+问题描述")
    suggestion: str = Field(default="", description="整体改写建议，无偏离可为空")


def extract_style_profile(
    provider: Provider, plot: str, user_style_hint: str = ""
) -> StyleProfile:
    """One-time upfront extraction of the novel's style anchors.

    Returns a full StyleProfile including a sample passage serving as the
    few-shot imitation benchmark for every later chapter.
    """
    hint = user_style_hint.strip() or "（无，请自行设定一种适合该剧情的统一文风）"
    request = CompletionRequest(
        messages=[
            ChatMessage(role="system", content=EXTRACT_SYSTEM),
            ChatMessage(role="user", content=f"剧情：{plot}\n\n风格要求：{hint}"),
        ]
    )
    profile = provider.complete_structured(request, StyleProfile)
    if not profile.sample_passage:
        raise ValueError("style extraction returned no sample_passage")
    return profile


def style_anchor_block(profile: StyleProfile) -> str:
    """Build the system anchor injected into every chapter-writing prompt."""
    lines = ["【本作品语言风格锚点】以下字段定义了全书统一的文风，写作时必须严格遵守："]
    for label, value in (
        ("文风基调", profile.tone),
        ("视角人称", profile.pov),
        ("叙事时态", profile.tense),
        ("用语特点", profile.diction),
    ):
        if value:
            lines.append(f"- {label}：{value}")
    if profile.sample_passage:
        lines.append("\n【风格样本】以下段落是本作品文风的模仿标杆，请保持相同的语气与节奏：\n")
        lines.append(profile.sample_passage)
    return "\n".join(lines)


def check_style_deviation(
    provider: Provider, profile: StyleProfile, chapter_text: str
) -> StyleDeviation:
    """Chapter-level style check: compare written text against the anchors."""
    request = CompletionRequest(
        messages=[
            ChatMessage(role="system", content=CHECK_SYSTEM),
            ChatMessage(role="user", content=style_anchor_block(profile)),
            ChatMessage(role="user", content=f"【章节原文】\n{chapter_text}"),
        ]
    )
    return provider.complete_structured(request, StyleDeviation)
