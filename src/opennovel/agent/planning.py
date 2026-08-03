"""Chapter/scene planning and scene writing (MVP step 5).

Four operations, all going through the `llm/` abstraction:
- `plan_chapters`: book-level chapter list from the plot (one call)
- `plan_scenes`: per-chapter scene outlines (one call per chapter)
- `write_scene`: one scene's prose (one call per scene)
- `rewrite_chapter`: one rewritten chapter pass after failed checks
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from opennovel.llm import ChatMessage, CompletionRequest, Provider
from opennovel.models import Scene

PLAN_CHAPTERS_SYSTEM = """你是小说大纲规划师。根据用户剧情生成章节列表：
- title：章节标题（简洁有韵味）
- focus：本章核心冲突或进展，一句话
- scene_count：本章场景数（2-4 为宜）
按剧情自然推进，总章节数不超过给定上限；不要出现与剧情无关的章节。"""

PLAN_SCENES_SYSTEM = """你是小说场景规划师。为指定章节规划场景大纲：
- summary：场景大纲，一句话说清本场景发生什么（时间/地点/动作/情绪）
按章节要点拆解 2-4 个场景，每个场景是一段连续叙事，场景间不要内容重复。"""

WRITE_SYSTEM = """你是小说作者。根据【风格锚点】和【剧情简报】写作指定场景的正文：
- 严格遵守风格锚点（语气/视角/用语/节奏），与全书保持一致
- 不得违背剧情简报中的事实，待回收伏笔不要提前揭露
- 结合【上一场景末段】自然衔接
- 只输出正文本身，不要标题、不要解释"""

REWRITE_SYSTEM = """你是修订编辑。根据检查意见重写章节正文：
- 修正所有指出的风格偏差与剧情矛盾
- 保留剧情推进与场景顺序，不要偏离原大纲
- 输出重写后的完整章节正文，只输出正文本身"""


class ChapterPlan(BaseModel):
    """One chapter in the book outline."""

    title: str = Field(description="章节标题")
    focus: str = Field(default="", description="本章核心冲突或进展，一句话")
    scene_count: int = Field(default=3, ge=1, le=6, description="本章场景数，建议 2-4")


class ChapterPlanList(BaseModel):
    chapters: list[ChapterPlan]


class ScenePlanList(BaseModel):
    scenes: list[Scene]


def plan_chapters(provider: Provider, plot: str, max_chapters: int) -> list[ChapterPlan]:
    """Book-level chapter list from the plot (one LLM call)."""
    request = CompletionRequest(
        messages=[
            ChatMessage(role="system", content=PLAN_CHAPTERS_SYSTEM),
            ChatMessage(role="user", content=f"剧情：\n{plot}\n\n最多 {max_chapters} 章"),
        ]
    )
    plans = provider.complete_structured(request, ChapterPlanList).chapters
    return plans[:max_chapters]


def plan_scenes(
    provider: Provider,
    plot: str,
    chapter_plan: ChapterPlan,
    style_anchor: str,
    plot_brief: str,
) -> list[Scene]:
    """Scene outlines for one chapter (one LLM call)."""
    request = CompletionRequest(
        messages=[
            ChatMessage(role="system", content=PLAN_SCENES_SYSTEM),
            ChatMessage(
                role="user",
                content=(
                    f"剧情：{plot}\n\n本章规划：{chapter_plan.title} — {chapter_plan.focus}\n"
                    f"风格锚点：{style_anchor}\n剧情简报：{plot_brief}"
                ),
            ),
        ]
    )
    return provider.complete_structured(request, ScenePlanList).scenes


def write_scene(
    provider: Provider,
    scene: Scene,
    style_anchor: str,
    plot_brief: str,
    prev_tail: str,
    target_chars: int,
) -> str:
    """Write one scene's prose (one LLM call). Returns the text."""
    request = CompletionRequest(
        messages=[
            ChatMessage(role="system", content=WRITE_SYSTEM),
            ChatMessage(
                role="user",
                content=(
                    f"风格锚点：\n{style_anchor}\n\n剧情简报：\n{plot_brief}\n\n"
                    f"【场景大纲】\n{scene.summary}\n\n"
                    f"【上一场景末段】\n{prev_tail or '（本章第一个场景）'}\n\n"
                    f"字数要求：约 {target_chars} 字"
                ),
            ),
        ]
    )
    return provider.complete(request).text.strip()


def rewrite_chapter(
    provider: Provider,
    chapter_text: str,
    style_deviation,
    plot_consistency,
    style_anchor: str,
) -> str:
    """One rewrite pass driven by the check reports. Returns new text."""
    report: list[str] = []
    if style_deviation is not None:
        lines = [f"【风格检查】偏离度 {style_deviation.score}", *style_deviation.deviations]
        if style_deviation.suggestion:
            lines.append(f"建议：{style_deviation.suggestion}")
        report.append("\n".join(lines))
    if plot_consistency is not None:
        lines = [f"【剧情检查】矛盾度 {plot_consistency.score}", *plot_consistency.contradictions]
        if plot_consistency.suggestion:
            lines.append(f"建议：{plot_consistency.suggestion}")
        report.append("\n".join(lines))
    request = CompletionRequest(
        messages=[
            ChatMessage(role="system", content=REWRITE_SYSTEM),
            ChatMessage(
                role="user",
                content=(
                    f"风格锚点：\n{style_anchor}\n\n检查报告：\n"
                    + "\n\n".join(report)
                    + f"\n\n【待重写章节原文】\n{chapter_text}"
                ),
            ),
        ]
    )
    return provider.complete(request).text.strip()
