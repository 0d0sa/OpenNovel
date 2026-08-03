"""Rich rendering helpers for the interactive UI.

Functions return renderables (Table/Panel/Group/Text); the `print_*` wrappers
render them to a console. This lets both the console REPL and the full-screen
app share the same presentation.
"""

from __future__ import annotations

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from opennovel.memory import StyleProfile
from opennovel.models import Novel

BANNER_TEXT = "OpenNovel — 小说写作 Agent（聊天输入 / 命令用 / 开头，输入 /help 查看帮助）"


def banner_text() -> Text:
    return Text(BANNER_TEXT, style="cyan bold")


def help_table() -> Table:
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
    return table


def status_view(novel: Novel) -> Group:
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
    state = novel.plot_state
    summary = Text(
        f"剧情状态：{len(state.characters)} 角色 / {len(state.events)} 事件 / "
        f"{len([s for s in state.setups if s.resolved_in is None])} 个未回收伏笔",
        style="dim",
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
    return Panel(body, title="风格锚点", border_style="cyan")


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
