"""Rich rendering helpers for the interactive UI.

Functions return renderables (Table/Panel/Group/Text); the `print_*` wrappers
render them to a console. This lets both the console REPL and the full-screen
app share the same presentation.
"""

from __future__ import annotations

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from opennovel.memory import StyleProfile
from opennovel.models import Novel
from opennovel.ui.theme import BRAND, ERROR, MUTED, SUBTLE, TEXT

BANNER_TEXT = "OpenNovel — 小说写作智能体"


def banner_text() -> Text:
    return Text(BANNER_TEXT, style=f"bold {BRAND}")


def welcome_panel(model: str = "") -> Panel:
    """Compact first-run card; detailed commands stay behind `/help`."""
    body = Text()
    body.append("OpenNovel\n", style=f"bold {BRAND}")
    body.append("把剧情写成长篇故事，并持续守住文风与剧情连贯性。\n\n", style=TEXT)
    body.append(">  输入 ", style=MUTED)
    body.append("/new", style=f"bold {TEXT}")
    body.append(" 创建作品，或直接描述你想写的故事\n", style=MUTED)
    body.append("   输入 ", style=MUTED)
    body.append("/help", style=f"bold {TEXT}")
    body.append(" 查看全部命令", style=MUTED)
    if model:
        body.append(f"\n\nmodel  {model}", style=f"dim {MUTED}")
    return Panel(
        body,
        box=box.ROUNDED,
        border_style=SUBTLE,
        padding=(1, 2),
        expand=False,
    )


def help_table() -> Table:
    table = Table(
        title="命令 / Commands",
        title_style=f"bold {TEXT}",
        show_header=False,
        box=box.SIMPLE,
        border_style=SUBTLE,
        padding=(0, 2),
    )
    table.add_column("命令", style=f"bold {BRAND}", no_wrap=True)
    table.add_column("说明", style=MUTED)
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
    return table


def status_view(novel: Novel) -> Group:
    table = Table(
        title=f"《{novel.title}》",
        title_style=f"bold {TEXT}",
        header_style=MUTED,
        border_style=SUBTLE,
        box=box.SIMPLE_HEAD,
        show_header=True,
    )
    table.add_column("章节", style=TEXT)
    table.add_column("字数", justify="right", style=MUTED)
    table.add_column("风格", justify="right", style=MUTED)
    table.add_column("剧情", justify="right", style=MUTED)
    for i, ch in enumerate(novel.chapters, 1):
        chars = sum(len(s.content) for s in ch.scenes)
        style_score = ch.style_report.score if ch.style_report else "-"
        plot_score = ch.plot_report.score if ch.plot_report else "-"
        table.add_row(f"第{i}章 {ch.title}", str(chars), str(style_score), str(plot_score))
    state = novel.plot_state
    summary = Text(
        f"剧情状态：{len(state.characters)} 角色 / {len(state.events)} 事件 / "
        f"{len([s for s in state.setups if s.resolved_in is None])} 个未回收伏笔",
        style=MUTED,
    )
    return Group(table, summary)


def style_panel(profile: StyleProfile) -> Panel:
    lines = [
        f"文风基调：{profile.tone or '-'}",
        f"视角人称：{profile.pov or '-'}",
        f"叙事时态：{profile.tense or '-'}",
        f"用语特点：{profile.diction or '-'}",
    ]
    body = "\n".join(lines)
    if profile.sample_passage:
        body += "\n\n[bold]风格样本：[/bold]\n" + profile.sample_passage
    return Panel(
        body,
        title=f"[{BRAND}]风格锚点[/]",
        title_align="left",
        border_style=SUBTLE,
        box=box.ROUNDED,
        padding=(1, 2),
    )


def checks_group(novel: Novel) -> Group:
    if novel is None or not novel.chapters:
        return Group(Text("还没有章节", style="yellow"))
    items: list = []
    for i, ch in enumerate(novel.chapters, 1):
        items.append(Text(f"第{i}章 {ch.title}", style="bold"))
        if ch.style_report is None and ch.plot_report is None:
            items.append(Text("  （未检查）", style="dim"))
        if ch.style_report is not None:
            r = ch.style_report
            color = "green" if r.score < 3 else "red"
            items.append(Text(f"  风格检查 偏离度 {r.score}/5", style=color))
            for d in r.deviations:
                items.append(Text(f"    - {d}", style="yellow"))
            if r.suggestion:
                items.append(Text(f"    建议：{r.suggestion}", style="dim"))
        if ch.plot_report is not None:
            r = ch.plot_report
            color = "green" if r.score < 3 else "red"
            items.append(Text(f"  剧情检查 矛盾度 {r.score}/5", style=color))
            for c in r.contradictions:
                items.append(Text(f"    - {c}", style="yellow"))
            if r.suggestion:
                items.append(Text(f"    建议：{r.suggestion}", style="dim"))
        items.append(Text(""))
    return Group(*items)


def error_text(message: str) -> Text:
    text = Text()
    text.append("x ", style=f"bold {ERROR}")
    text.append(message, style=ERROR)
    return text


# --- console wrappers (console REPL / tests) ---


def print_banner(console: Console) -> None:
    console.print(banner_text())


def print_help(console: Console) -> None:
    console.print(help_table())


def print_status(console: Console, novel: Novel) -> None:
    if novel is None:
        console.print("[yellow]尚未开始任何书，先用 /new 开始[/yellow]")
        return
    console.print(status_view(novel))


def print_style(console: Console, profile: StyleProfile) -> None:
    if profile is None:
        console.print("[yellow]尚未开始任何书，先用 /new 开始[/yellow]")
        return
    console.print(style_panel(profile))


def print_checks(console: Console, novel: Novel) -> None:
    console.print(checks_group(novel))
