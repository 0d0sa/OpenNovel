"""Chat stream: user/assistant/system messages rendered as a conversation.

Two render paths:
- `ChatStream`: prints to a rich Console (console REPL, tests)
- `ChatView` + `render_ansi`: produce ANSI text for the full-screen app
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console, Group
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

from opennovel.models import Novel

USER_PREFIX = "[bold cyan]你[/bold cyan]"
ASSISTANT_PREFIX = "[bold green]OpenNovel[/bold green]"
SYSTEM_PREFIX = "[bold magenta]系统[/bold magenta]"


def render_ansi(renderable, width: int = 100) -> str:
    """Render a rich object to an ANSI string for prompt_toolkit."""
    buf = Console(
        color_system="truecolor",
        force_terminal=True,
        width=width,
        file=StringIO(),
    )
    buf.print(renderable)
    return buf.file.getvalue()


class ChatView:
    """Message list rendered as one ANSI text block (full-screen app)."""

    def __init__(self, width: int = 100):
        self.width = width
        self.messages: list[tuple[str, str]] = []  # (role, text) metadata
        self._texts: list[str] = []
        self._parts: list[str] = []

    @property
    def ansi_text(self) -> str:
        base = "".join(self._texts)
        if self._parts:
            base += render_ansi(Text("".join(self._parts)), self.width)
        return base

    def add_user(self, text: str) -> None:
        self.messages.append(("user", text))
        self._append(Text.from_markup(f"{USER_PREFIX}：{escape(text)}"))

    def add_assistant(self, text: str) -> None:
        self.messages.append(("assistant", text))
        self._append(Text.from_markup(f"{ASSISTANT_PREFIX}：{escape(text)}"))

    def add_system(self, renderable) -> None:
        self.messages.append(("system", str(renderable)))
        self._append(renderable)

    def begin_stream(self) -> None:
        self._parts = []
        self._append(Text.from_markup(f"{ASSISTANT_PREFIX}："), end="")

    def feed(self, token: str) -> None:
        self._parts.append(token)

    def end_stream(self) -> None:
        text = "".join(self._parts)
        self._parts = []
        self.messages.append(("assistant", text))
        if text:
            self._append(Text(text), end="\n")

    def _append(self, renderable, end: str = "\n") -> None:
        self._texts.append(render_ansi(renderable, self.width).rstrip() + end)

    @staticmethod
    def stage_panel(stage: str) -> Panel:
        return Panel(Text(stage, style="bold yellow"), border_style="blue", title="进度", expand=False)

    @staticmethod
    def chapter_card(novel: Novel, idx: int) -> Panel:
        chapter = novel.chapters[idx - 1]
        chars = sum(len(s.content) for s in chapter.scenes)
        style_score = chapter.style_report.score if chapter.style_report else "-"
        plot_score = chapter.plot_report.score if chapter.plot_report else "-"
        body = (
            f"第{idx}章 {chapter.title}\n"
            f"字数：{chars}  风格检查：{style_score}/5  剧情检查：{plot_score}/5"
        )
        return Panel(body, border_style="green", title="章节完成", expand=False)

    @staticmethod
    def summary_card(novel: Novel) -> Panel:
        chars = sum(len(s.content) for ch in novel.chapters for s in ch.scenes)
        setups = [s for s in novel.plot_state.setups if s.resolved_in is None]
        body = (
            f"《{novel.title}》{len(novel.chapters)} 章，约 {chars} 字\n"
            f"{len(novel.plot_state.characters)} 角色 / {len(novel.plot_state.events)} 事件 / "
            f"{len(setups)} 个未回收伏笔"
        )
        return Panel(body, border_style="green", title="成书", expand=False)


class ChatStream:
    """In-session chat history plus rendering helpers."""

    def __init__(self, console: Console):
        self.console = console
        self.messages: list[tuple[str, str]] = []  # (role, text); role in user/assistant/system
        self._parts: list[str] = []

    def add_user(self, text: str) -> None:
        self.messages.append(("user", text))
        self.console.print(f"{USER_PREFIX}：{text}")

    def add_assistant(self, text: str) -> None:
        self.messages.append(("assistant", text))
        self.console.print(f"{ASSISTANT_PREFIX}：{text}")

    def add_system(self, renderable) -> None:
        self.messages.append(("system", str(renderable)))
        self.console.print(renderable)

    def stream_assistant(self, chunks) -> str:
        """Stream prose inside one assistant message; returns the full text."""
        self.console.print(f"{ASSISTANT_PREFIX}：", end="")
        parts: list[str] = []
        for chunk in chunks:
            parts.append(chunk)
            self.console.print(chunk, end="", highlight=False)
        self.console.print()
        text = "".join(parts)
        self.messages.append(("assistant", text))
        return text

    def begin_stream(self) -> None:
        """Start a push-based assistant stream (used with on_token callbacks)."""
        self.console.print(f"{ASSISTANT_PREFIX}：", end="")
        self._parts = []

    def feed(self, token: str) -> None:
        self._parts.append(token)
        self.console.print(token, end="", highlight=False)

    def end_stream(self) -> None:
        self.console.print()
        text = "".join(self._parts)
        self.messages.append(("assistant", text))
        self._parts = []

    @staticmethod
    def stage_panel(stage: str) -> Panel:
        return Panel(Text(stage, style="bold yellow"), border_style="blue", title="进度", expand=False)

    @staticmethod
    def chapter_card(novel: Novel, idx: int) -> Panel:
        chapter = novel.chapters[idx - 1]
        chars = sum(len(s.content) for s in chapter.scenes)
        style_score = chapter.style_report.score if chapter.style_report else "-"
        plot_score = chapter.plot_report.score if chapter.plot_report else "-"
        body = (
            f"第{idx}章 {chapter.title}\n"
            f"字数：{chars}  风格检查：{style_score}/5  剧情检查：{plot_score}/5"
        )
        return Panel(body, border_style="green", title="章节完成", expand=False)

    @staticmethod
    def summary_card(novel: Novel) -> Panel:
        chars = sum(len(s.content) for ch in novel.chapters for s in ch.scenes)
        setups = [s for s in novel.plot_state.setups if s.resolved_in is None]
        body = (
            f"《{novel.title}》{len(novel.chapters)} 章，约 {chars} 字\n"
            f"{len(novel.plot_state.characters)} 角色 / {len(novel.plot_state.events)} 事件 / "
            f"{len(setups)} 个未回收伏笔"
        )
        return Panel(body, border_style="green", title="成书", expand=False)

    @staticmethod
    def group(*renderables) -> Group:
        return Group(*renderables)
