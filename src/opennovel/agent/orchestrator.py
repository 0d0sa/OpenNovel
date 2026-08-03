"""Agent orchestration: plot -> chapters (MVP step 5).

Per-chapter order (per docs/plan/plot_state.md): inject brief (old state) ->
write scenes -> run checks against the old state -> then update the state.
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
) -> Novel:
    """Full pipeline: style extraction -> outline -> per-chapter scenes.

    The novel is persisted to `settings.output_dir/<title>/novel.json` after
    every chapter, and a plain-text copy `novel.txt` is exported at the end.
    """
    profile = extract_style_profile(provider, plot, style_hint)
    novel = Novel(title=title, plot=plot, style_profile=profile)
    anchor = style_anchor_block(profile)

    plans = plan_chapters(provider, plot, settings.max_chapters)
    if on_progress:
        on_progress(f"全书规划：{len(plans)} 章")

    for idx, plan in enumerate(plans, start=1):
        brief = plot_state_brief(novel.plot_state)
        scenes = plan_scenes(provider, plot, plan, anchor, brief)
        if not scenes:
            scenes = [Scene(summary=plan.focus or plan.title)]

        prev_tail = ""
        for scene in scenes:
            target = max(settings.chapter_target_chars // len(scenes), 200)
            text = write_scene(provider, scene, anchor, brief, prev_tail, target)
            scene.content = text
            scene.status = SceneStatus.WRITTEN
            prev_tail = text[-TAIL_CHARS:]
        chapter_text = "\n\n".join(s.content for s in scenes)

        style_dev = (
            check_style_deviation(provider, profile, chapter_text)
            if settings.style_check
            else None
        )
        plot_cons = (
            check_plot_consistency(provider, novel.plot_state, chapter_text, idx)
            if settings.plot_check
            else None
        )
        if (
            style_dev is not None and style_dev.score >= REWRITE_THRESHOLD
        ) or (plot_cons is not None and plot_cons.score >= REWRITE_THRESHOLD):
            if on_progress:
                on_progress(
                    f"  第{idx}章检查未过"
                    f"（风格 {style_dev.score if style_dev else 0}"
                    f"/剧情 {plot_cons.score if plot_cons else 0}），重写一次"
                )
            chapter_text = rewrite_chapter(provider, chapter_text, style_dev, plot_cons, anchor)
            scenes = [
                Scene(summary=f"第{idx}章（重写稿）", content=chapter_text, status=SceneStatus.WRITTEN)
            ]

        novel.plot_state = update_plot_state(provider, chapter_text, idx, novel.plot_state)
        novel.chapters.append(Chapter(title=plan.title, outline=plan.focus, scenes=scenes))
        save_novel(novel, settings.output_dir / novel.title / "novel.json")
        if on_progress:
            on_progress(f"第{idx}章完成：{plan.title}")

    export_novel_text(novel, settings.output_dir / novel.title / "novel.txt")
    return novel


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
