"""Chat-style interactive session (Claude Code like).

`opennovel` with no subcommand enters. `/` commands and free-text prompts are
both accepted in the same input box; free text goes through LLM intent routing
(`agent/intent.py`). Command dispatch stays in `handle_command` (pure-ish,
testable without a terminal).
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from opennovel.agent import IntentKind, classify_intent, write_novel
from opennovel.config import Settings
from opennovel.llm import Provider
from opennovel.models import Scene, SceneStatus, save_novel
from opennovel.ui.chat import ChatStream
from opennovel.ui.display import print_banner, print_checks, print_help, print_status, print_style
from opennovel.ui.input import ChatInput


@dataclass
class Session:
    provider: Provider
    settings: Settings
    console: Console
    chat: ChatStream
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
            if line:
                self.chat.add_user(line)
            return line

    def say(self, text: str) -> None:
        self.console.print(text)


def run_repl(provider: Provider, settings: Settings) -> int:
    console = Console()
    session = Session(provider=provider, settings=settings, console=console, chat=ChatStream(console))
    print_banner(console)
    print_help(console)
    inp = ChatInput()
    while True:
        try:
            line = inp.prompt()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见[/dim]")
            return 0
        line = line.strip()
        if not line:
            continue
        session.history.append(line)
        session.chat.add_user(line)
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
        _route_free_text(session, line)
    return True


def _route_free_text(session: Session, line: str) -> None:
    intent = classify_intent(session.provider, line)
    kind = intent.kind
    if kind == IntentKind.REWRITE_CHAPTER and intent.chapter_no >= 1:
        _cmd_rewrite(session, [str(intent.chapter_no)])
    elif kind == IntentKind.START_NEW:
        _cmd_new(session, [])
    elif kind == IntentKind.WRITE_NOW:
        _cmd_write(session)
    elif kind == IntentKind.STATUS:
        print_status(session.console, session.novel)
    elif kind == IntentKind.CHECKS:
        print_checks(session.console, session.novel)
    elif kind == IntentKind.HELP:
        print_help(session.console)
    else:  # append_plot / other
        if kind == IntentKind.OTHER and intent.suggestion:
            session.say(f"[dim]（{intent.suggestion}）[/dim]")
        _append_plot(session, line)


def _append_plot(session: Session, line: str) -> None:
    if not session.plot:
        session.say("[yellow]还没有开始新书，先 /new 创建[/yellow]")
        return
    session.plot = session.plot.rstrip() + "\n" + line
    session.say("[dim]已追加到剧情[/dim]")


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
    session.chat.add_system(session.chat.stage_panel(f"已创建：《{title}》，说 /write 或“开始写作”"))
    session.say("[dim]聊天输入可理解为自然语言指令（如“把第二章重写得更紧张”）[/dim]")


def _cmd_write(session: Session) -> None:
    if not session.plot:
        session.say("[yellow]还没有开始新书，先 /new 创建[/yellow]")
        return

    def on_stage(stage: str) -> None:
        session.chat.add_system(session.chat.stage_panel(stage))

    session.chat.begin_stream()
    novel = write_novel(
        session.provider,
        session.settings,
        session.title,
        session.plot,
        session.style_hint,
        on_progress=session.say,
        on_stage=on_stage,
        on_token=session.chat.feed,
    )
    session.chat.end_stream()
    session.novel = novel
    session.chat.add_system(session.chat.summary_card(novel))
    path = session.settings.output_dir / novel.title / "novel.json"
    session.say(f"[dim]成书：{path}（/checks 查看检查报告）[/dim]")


def _cmd_rewrite(session: Session, args: list[str]) -> None:
    novel = session.novel
    if novel is None:
        session.say("[yellow]还没有章节可重写[/yellow]")
        return
    if not args:
        session.say("[red]用法：/rewrite N 或直接说“重写第N章”[/red]")
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
    session.chat.add_system(session.chat.stage_panel(f"重写第{idx}章…"))

    session.chat.begin_stream()
    new_text = rewrite_chapter(
        session.provider,
        text,
        chapter.style_report,
        chapter.plot_report,
        style_anchor_block(novel.style_profile),
        stream_callback=session.chat.feed,
    )
    session.chat.end_stream()
    chapter.scenes = [Scene(summary="重写稿", content=new_text, status=SceneStatus.WRITTEN)]
    chapter.style_report = None
    chapter.plot_report = None
    save_novel(novel, session.settings.output_dir / novel.title / "novel.json")
    session.say(f"[green]第{idx}章已重写并保存[/green]")
