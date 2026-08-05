"""Agent orchestration: plot -> chapters (MVP step 5, v2 refactor).

Per-chapter order (per docs/plan/plot_state.md): inject brief (old state) ->
write scenes -> run checks against the old state -> then update the state.

`write_one_chapter` is the single-chapter pipeline unit; the batch
`write_novel` and the agent tool `write_chapter` both reuse it.
"""

from __future__ import annotations

from pathlib import Path

from opennovel.agent.planning import (
    ChapterPlan,
    plan_chapters,
    plan_scenes,
    rewrite_chapter,
    write_scene,
)
from opennovel.config import Settings
from opennovel.llm import Provider
from opennovel.memory import (
    check_plot_consistency,
    check_style_deviation,
    extract_style_profile,
    plot_state_brief,
    style_anchor_block,
    update_plot_state,
)
from opennovel.models import Chapter, Novel, Scene, SceneStatus, save_novel

REWRITE_THRESHOLD = 3
TAIL_CHARS = 200


def write_novel(
    provider: Provider,
    settings: Settings,
    title: str,
    plot: str,
    style_hint: str = "",
    on_progress=None,
    on_stage=None,
    on_token=None,
) -> Novel:
    """Full pipeline: style extraction -> outline -> per-chapter scenes.

    The novel is persisted to `settings.output_dir/<title>/novel.json` after
    every chapter, and a plain-text copy `novel.txt` is exported at the end.

    Callbacks (all optional, keep the pipeline UI-free):
    - on_progress(msg: str): human-readable progress lines
    - on_stage(stage: str): current stage label (for live panels)
    - on_token(text: str): when set, scene prose is streamed token by token
    """
    if on_stage:
        on_stage("提取风格锚点")
    profile = extract_style_profile(provider, plot, style_hint)
    novel = Novel(title=title, plot=plot, style_profile=profile)
    anchor = style_anchor_block(profile)

    if on_stage:
        on_stage("规划全书大纲")
    plans = plan_chapters(provider, plot, settings.max_chapters)
    novel.outline = plans
    if on_progress:
        on_progress(f"全书规划：{len(plans)} 章")

    for idx, plan in enumerate(plans, start=1):
        if on_stage:
            on_stage(f"第{idx}章 规划场景")
        chapter = write_one_chapter(
            provider,
            settings,
            novel,
            idx,
            plan,
            on_progress=on_progress,
            on_stage=on_stage,
            on_token=on_token,
        )
        novel.chapters.append(chapter)
        save_novel(novel, settings.output_dir / novel.title / "novel.json")
        if on_progress:
            on_progress(f"第{idx}章完成：{plan.title}")

    export_novel_text(novel, settings.output_dir / novel.title / "novel.txt")
    return novel


def write_one_chapter(
    provider: Provider,
    settings: Settings,
    novel: Novel,
    chapter_no: int,
    plan: ChapterPlan,
    *,
    scenes: list[Scene] | None = None,
    on_progress=None,
    on_stage=None,
    on_token=None,
) -> Chapter:
    """Write one chapter (plan scenes -> write scenes -> checks -> update
    plot state). Mutates `novel.plot_state`; persistence is up to the caller.

    Pass pre-planned `scenes` (status PLANNED) to skip the planning call.
    """
    anchor = style_anchor_block(novel.style_profile)
    brief = plot_state_brief(novel.plot_state)
    if scenes is None:
        if on_stage:
            on_stage(f"第{chapter_no}章 规划场景")
        scenes = plan_scenes(provider, novel.plot, plan, anchor, brief)
    if not scenes:
        scenes = [Scene(summary=plan.focus or plan.title)]

    prev_tail = ""
    for j, scene in enumerate(scenes, 1):
        if on_stage:
            on_stage(f"第{chapter_no}章 写作场景 {j}/{len(scenes)}")
        target = max(settings.chapter_target_chars // len(scenes), 200)
        text = write_scene(
            provider,
            scene,
            anchor,
            brief,
            prev_tail,
            target,
            stream_callback=on_token,
        )
        scene.content = text
        scene.status = SceneStatus.WRITTEN
        prev_tail = text[-TAIL_CHARS:]
    chapter_text = "\n\n".join(s.content for s in scenes)

    style_dev = None
    plot_cons = None
    if settings.style_check:
        if on_stage:
            on_stage(f"第{chapter_no}章 风格检查")
        style_dev = check_style_deviation(provider, novel.style_profile, chapter_text)
    if settings.plot_check:
        if on_stage:
            on_stage(f"第{chapter_no}章 剧情一致性检查")
        plot_cons = check_plot_consistency(provider, novel.plot_state, chapter_text, chapter_no)
    if (
        style_dev is not None and style_dev.score >= REWRITE_THRESHOLD
    ) or (plot_cons is not None and plot_cons.score >= REWRITE_THRESHOLD):
        if on_progress:
            on_progress(
                f"  第{chapter_no}章检查未过"
                f"（风格 {style_dev.score if style_dev else 0}"
                f"/剧情 {plot_cons.score if plot_cons else 0}），重写一次"
            )
        if on_stage:
            on_stage(f"第{chapter_no}章 重写")
        chapter_text = rewrite_chapter(
            provider, chapter_text, style_dev, plot_cons, anchor, stream_callback=on_token
        )
        scenes = [
            Scene(summary=f"第{chapter_no}章（重写稿）", content=chapter_text, status=SceneStatus.WRITTEN)
        ]

    if on_stage:
        on_stage(f"第{chapter_no}章 更新剧情状态")
    novel.plot_state = update_plot_state(provider, chapter_text, chapter_no, novel.plot_state)
    return Chapter(
        title=plan.title,
        outline=plan.focus,
        scenes=scenes,
        style_report=style_dev,
        plot_report=plot_cons,
    )


def export_novel_text(novel: Novel, path: Path) -> Path:
    """Export the finished novel as plain text for reading."""
    parts = [novel.title, ""]
    for idx, chapter in enumerate(novel.chapters, 1):
        parts.append(f"第{idx}章 {chapter.title}")
        parts.append("")
        parts.append(chapter_text(chapter))
        parts.append("")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def chapter_text(chapter: Chapter) -> str:
    return "\n\n".join(s.content for s in chapter.scenes if s.content)
