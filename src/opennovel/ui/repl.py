"""Interactive REPL session (like a CLI coding agent UI).

Run `opennovel` with no subcommand to enter. Commands are dispatched through
`handle_command(session, line)` — a pure-ish function that tests can drive
without a real terminal.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from opennovel.agent import write_novel
from opennovel.config import Settings
from opennovel.llm import Provider
from opennovel.models import Scene, SceneStatus, load_novel, save_novel
from opennovel.ui.display import (
    print_banner,
    print_checks,
    print_help,
    print_status,
    print_style,
)


@dataclass
class Session:
    provider: Provider
    settings: Settings
    console: Console
    title: str = ""
    plot: str = ""
    style_hint: str = ""
    novel: object = None
    history: list[str] = field(default_factory=list)
    exiting: bool = False

    def ask(self, prompt: str) -> str:
        """Read a line, dispatching `/` commands instead of treating them as answers."""
        while True:
            line = self.console.input(f"[bold cyan]{prompt}[/bold cyan] ").strip()
            if line.startswith("/"):
                handle_command(self, line)
                if self.exiting:
                    return ""
                self.console.print("[dim]命令已执行，请继续回答：[/dim]" + prompt)
                continue
            return line

    def say(self, text: str) -> None:
        self.console.print(text)


def run_repl(provider: Provider, settings: Settings) -> int:
    console = Console()
    session = Session(provider=provider, settings=settings, console=console)
    print_banner(console)
    print_help(console)
    while True:
        try:
            line = console.input("[bold green]opennovel> [/bold green]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见[/dim]")
            return 0
        line = line.strip()
        if not line:
            continue
        session.history.append(line)
        try:
            if not handle_command(session, line) or session.exiting:
                return 0
        except Exception as exc:
            console.print(f"[red]错误：{exc}[/red]")


def handle_command(session: Session, line: str) -> bool:
    """Process one input line. Returns False to exit the session."""
    if line.startswith("/"):
        parts = shlex.split(line)
        cmd = parts[0].lower()
        args = parts[1:]
        if cmd == "/exit":
            session.exiting = True
            return False
        if cmd == "/help":
            print_help(session.console)
        elif cmd == "/new":
            _cmd_new(session, args)
        elif cmd == "/write":
            _cmd_write(session)
        elif cmd == "/status":
            print_status(session.console, session.novel)
        elif cmd == "/style":
            print_style(session.console, getattr(session.novel, "style_profile", None))
        elif cmd == "/checks":
            print_checks(session.console, session.novel)
        elif cmd == "/rewrite":
            _cmd_rewrite(session, args)
        else:
            session.say(f"[red]未知命令：{cmd}（/help 查看可用命令）[/red]")
    else:
        _append_plot(session, line)
    return True


def _append_plot(session: Session, line: str) -> None:
    if not session.plot:
        session.say("[yellow]还没有开始新书，先 /new 创建[/yellow]")
        return
    session.plot = session.plot.rstrip() + "\n" + line
    session.say("[dim]已追加到剧情：[/dim]" + line)


def _cmd_new(session: Session, args: list[str]) -> None:
    title = ""
    plot_file = None
    style_hint = ""
    i = 0
    while i < len(args):
        if args[i] == "--title" and i + 1 < len(args):
            title = args[i + 1]
            i += 2
        elif args[i] == "--plot-file" and i + 1 < len(args):
            plot_file = args[i + 1]
            i += 2
        elif args[i] == "--style" and i + 1 < len(args):
            style_hint = args[i + 1]
            i += 2
        else:
            session.say(f"[red]未知参数：{args[i]}（支持 --title / --plot-file / --style）[/red]")
            return
    title = title or session.ask("书名：")
    if session.exiting:
        return
    if not title:
        session.say("[red]书名不能为空[/red]")
        return
    plot = ""
    if plot_file:
        try:
            plot = Path(plot_file).read_text(encoding="utf-8")
        except OSError as exc:
            session.say(f"[red]读取剧情文件失败：{exc}[/red]")
            return
    else:
        plot = session.ask("剧情（一句话即可）：")
        if session.exiting:
            return
    if not plot:
        session.say("[red]剧情不能为空[/red]")
        return
    style_hint = style_hint or session.ask("风格描述（可回车跳过）：")
    if session.exiting:
        return
    session.title = title
    session.plot = plot
    session.style_hint = style_hint
    session.novel = None
    session.say(f"[green]已创建：《{title}》，/write 开始写作[/green]")


def _cmd_write(session: Session) -> None:
    if not session.plot:
        session.say("[yellow]还没有开始新书，先 /new 创建[/yellow]")
        return

    def on_stage(stage: str) -> None:
        session.console.print(
            Panel(stage, border_style="blue", title="进度", expand=False)
        )

    def on_token(token: str) -> None:
        session.console.print(token, end="", highlight=False)

    novel = write_novel(
        session.provider,
        session.settings,
        session.title,
        session.plot,
        session.style_hint,
        on_progress=session.say,
        on_stage=on_stage,
        on_token=on_token,
    )
    session.novel = novel
    chars = sum(len(s.content) for ch in novel.chapters for s in ch.scenes)
    session.console.print("\n")
    session.say(f"[green]完成：《{novel.title}》{len(novel.chapters)} 章，约 {chars} 字[/green]")
    path = session.settings.output_dir / novel.title / "novel.json"
    session.say(f"[dim]成书：{path}（/checks 查看检查报告）[/dim]")


def _cmd_rewrite(session: Session, args: list[str]) -> None:
    novel = session.novel
    if novel is None:
        session.say("[yellow]还没有章节可重写[/yellow]")
        return
    if not args:
        session.say("[red]用法：/rewrite N[/red]")
        return
    try:
        idx = int(args[0])
    except ValueError:
        session.say("[red]章节号必须是数字[/red]")
        return
    if not 1 <= idx <= len(novel.chapters):
        session.say(f"[red]章节号超出范围（1-{len(novel.chapters)}）[/red]")
        return

    from opennovel.agent.planning import rewrite_chapter
    from opennovel.memory import style_anchor_block

    chapter = novel.chapters[idx - 1]
    text = "\n\n".join(s.content for s in chapter.scenes if s.content)
    if not text:
        session.say("[red]该章无正文[/red]")
        return
    session.console.print(Panel(f"重写第{idx}章…", border_style="blue", expand=False))

    def on_token(token: str) -> None:
        session.console.print(token, end="", highlight=False)

    new_text = rewrite_chapter(
        session.provider,
        text,
        chapter.style_report,
        chapter.plot_report,
        style_anchor_block(novel.style_profile),
        stream_callback=on_token,
    )
    chapter.scenes = [Scene(summary="重写稿", content=new_text, status=SceneStatus.WRITTEN)]
    chapter.style_report = None
    chapter.plot_report = None
    save_novel(novel, session.settings.output_dir / novel.title / "novel.json")
    session.console.print("\n")
    session.say(f"[green]第{idx}章已重写并保存[/green]")


def load_existing(session: Session) -> None:
    """Load a previously written novel by title (used by /open)."""
    path = session.settings.output_dir / session.title / "novel.json"
    if path.exists():
        session.novel = load_novel(path)
