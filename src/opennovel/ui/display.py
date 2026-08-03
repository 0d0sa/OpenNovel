"""Rich rendering helpers for the interactive UI."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from opennovel.memory import StyleProfile
from opennovel.models import Novel

BANNER = """[bold cyan]OpenNovel[/bold cyan] — 小说写作 Agent
输入 [bold]/help[/bold] 查看命令，[bold]/exit[/bold] 退出。自由输入 = 追加剧情补充。"""


def print_banner(console: Console) -> None:
    console.print(BANNER, style="cyan")


def print_help(console: Console) -> None:
    table = Table(title="命令", show_header=False, box=None, padding=(0, 2))
    table.add_column("命令", style="bold")
    table.add_column("说明")
    for cmd, desc in (
        ("/new", "开始一本新书（书名 / 剧情 / 风格）"),
        ("/write", "写作当前这本书"),
        ("/status", "当前书概览：章节数 / 各章字数 / 剧情状态"),
        ("/style", "查看当前风格锚点"),
        ("/checks", "查看各章检查报告"),
        ("/rewrite N", "手动重写第 N 章"),
        ("/help", "显示本帮助"),
        ("/exit", "退出"),
    ):
        table.add_row(cmd, desc)
    console.print(table)


def print_status(console: Console, novel: Novel) -> None:
    if novel is None:
        console.print("[yellow]尚未开始任何书，先用 /new 开始[/yellow]")
        return
    table = Table(title=f"《{novel.title}》", show_header=True)
    table.add_column("章节", style="bold")
    table.add_column("字数", justify="right")
    table.add_column("风格检查", justify="right")
    table.add_column("剧情检查", justify="right")
    for i, ch in enumerate(novel.chapters, 1):
        chars = sum(len(s.content) for s in ch.scenes)
        style_score = ch.style_report.score if ch.style_report else "-"
        plot_score = ch.plot_report.score if ch.plot_report else "-"
        table.add_row(f"第{i}章 {ch.title}", str(chars), str(style_score), str(plot_score))
    console.print(table)
    state = novel.plot_state
    console.print(
        f"[dim]剧情状态：{len(state.characters)} 角色 / {len(state.events)} 事件 / "
        f"{len([s for s in state.setups if s.resolved_in is None])} 个未回收伏笔[/dim]"
    )


def print_style(console: Console, profile: StyleProfile) -> None:
    if profile is None:
        console.print("[yellow]尚未开始任何书，先用 /new 开始[/yellow]")
        return
    lines = [
        f"文风基调：{profile.tone or '-'}",
        f"视角人称：{profile.pov or '-'}",
        f"叙事时态：{profile.tense or '-'}",
        f"用语特点：{profile.diction or '-'}",
    ]
    body = "\n".join(lines)
    if profile.sample_passage:
        body += "\n\n[bold]风格样本：[/bold]\n" + profile.sample_passage
    console.print(Panel(body, title="风格锚点", border_style="cyan"))


def print_checks(console: Console, novel: Novel) -> None:
    if novel is None or not novel.chapters:
        console.print("[yellow]还没有章节[/yellow]")
        return
    for i, ch in enumerate(novel.chapters, 1):
        console.print(f"\n[bold]第{i}章 {ch.title}[/bold]")
        if ch.style_report is None and ch.plot_report is None:
            console.print("  [dim]（未检查）[/dim]")
        if ch.style_report is not None:
            r = ch.style_report
            color = "green" if r.score < 3 else "red"
            console.print(f"  [bold]风格检查[/bold] 偏离度 [{color}]{r.score}/5[/{color}]")
            for d in r.deviations:
                console.print(f"    [yellow]- {d}[/yellow]")
            if r.suggestion:
                console.print(f"    [dim]建议：{r.suggestion}[/dim]")
        if ch.plot_report is not None:
            r = ch.plot_report
            color = "green" if r.score < 3 else "red"
            console.print(f"  [bold]剧情检查[/bold] 矛盾度 [{color}]{r.score}/5[/{color}]")
            for c in r.contradictions:
                console.print(f"    [yellow]- {c}[/yellow]")
            if r.suggestion:
                console.print(f"    [dim]建议：{r.suggestion}[/dim]")


def print_stage_panel(console: Console, stage: str) -> None:
    console.print(Panel(Text(stage, style="bold yellow"), border_style="blue", title="进度"))


def prompt_text(console: Console, prompt: str) -> str:
    return console.input(f"[bold cyan]{prompt}[/bold cyan] ").strip()
