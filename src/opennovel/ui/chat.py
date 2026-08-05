"""Chat stream: user/assistant/system messages rendered as a conversation.

Two render paths:
- `ChatStream`: prints to a rich Console (console REPL, tests)
- `ChatView` + `render_ansi`: produce ANSI text for the full-screen app
"""

from __future__ import annotations

from io import StringIO

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from opennovel.models import Novel
from opennovel.ui.theme import ACCENT, BRAND, MUTED, SUCCESS, TEXT, WARNING

USER_PREFIX = f"[bold {ACCENT}]>[/bold {ACCENT}]"
ASSISTANT_PREFIX = f"[bold {BRAND}]*[/bold {BRAND}] [bold {TEXT}]OpenNovel[/bold {TEXT}]"
SYSTEM_PREFIX = f"[bold {MUTED}]-[/bold {MUTED}]"


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

    def reset(self) -> None:
        """Clear all messages and rendered text (used when switching sessions)."""
        self.messages = []
        self._texts = []
        self._parts = []

    @property
    def ansi_text(self) -> str:
        base = "".join(self._texts)
        if self._parts:
            base += render_ansi(Text("".join(self._parts)), self.width)
        return base

    def add_user(self, text: str) -> None:
        self.messages.append(("user", text))
        self._append(_user_message(text))

    def add_assistant(self, text: str) -> None:
        self.messages.append(("assistant", text))
        self._append(_assistant_message(text))

    def add_system(self, renderable) -> None:
        self.messages.append(("system", str(renderable)))
        self._append(renderable)

    def begin_stream(self) -> None:
        self._parts = []
        self._append(_assistant_heading())

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
    def stage_panel(stage: str) -> Text:
        return _stage_status(stage)

    @staticmethod
    def chapter_card(novel: Novel, idx: int) -> Panel:
        return _chapter_card(novel, idx)

    @staticmethod
    def summary_card(novel: Novel) -> Panel:
        return _summary_card(novel)


class ChatStream:
    """In-session chat history plus rendering helpers."""

    def __init__(self, console: Console):
        self.console = console
        self.messages: list[tuple[str, str]] = []  # (role, text); role in user/assistant/system
        self._parts: list[str] = []

    def reset(self) -> None:
        """Clear all messages and streamed parts (used when switching sessions)."""
        self.messages = []
        self._parts = []

    def add_user(self, text: str) -> None:
        self.messages.append(("user", text))
        self.console.print(_user_message(text))

    def add_assistant(self, text: str) -> None:
        self.messages.append(("assistant", text))
        self.console.print(_assistant_message(text))

    def add_system(self, renderable) -> None:
        self.messages.append(("system", str(renderable)))
        self.console.print(renderable)

    def stream_assistant(self, chunks) -> str:
        """Stream prose inside one assistant message; returns the full text."""
        self.console.print(_assistant_heading())
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
        self.console.print(_assistant_heading())
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
    def stage_panel(stage: str) -> Text:
        return _stage_status(stage)

    @staticmethod
    def chapter_card(novel: Novel, idx: int) -> Panel:
        return _chapter_card(novel, idx)

    @staticmethod
    def summary_card(novel: Novel) -> Panel:
        return _summary_card(novel)

    @staticmethod
    def group(*renderables) -> Group:
        return Group(*renderables)


def _user_message(text: str) -> Text:
    message = Text()
    message.append("> ", style=f"bold {ACCENT}")
    message.append(text, style=f"bold {TEXT}")
    return message


def _assistant_heading() -> Text:
    heading = Text()
    heading.append("* ", style=f"bold {BRAND}")
    heading.append("OpenNovel", style=f"bold {TEXT}")
    return heading


def _assistant_message(text: str) -> Text:
    message = _assistant_heading()
    message.append("\n")
    message.append(text, style=TEXT)
    return message


def _stage_status(stage: str) -> Text:
    status = Text()
    status.append("- ", style=f"bold {WARNING}")
    status.append(stage, style=MUTED)
    return status


def _chapter_card(novel: Novel, idx: int) -> Panel:
    chapter = novel.chapters[idx - 1]
    chars = sum(len(s.content) for s in chapter.scenes)
    style_score = chapter.style_report.score if chapter.style_report else "-"
    plot_score = chapter.plot_report.score if chapter.plot_report else "-"
    body = Text()
    body.append(f"第{idx}章  {chapter.title}\n", style=f"bold {TEXT}")
    body.append(
        f"{chars} 字   风格 {style_score}/5   剧情 {plot_score}/5",
        style=MUTED,
    )
    return Panel(
        body,
        box=box.ROUNDED,
        border_style=SUBTLE_COLOR,
        title=f"[{SUCCESS}]done 章节完成[/]",
        title_align="left",
        padding=(0, 1),
        expand=False,
    )


def _summary_card(novel: Novel) -> Panel:
    chars = sum(len(s.content) for ch in novel.chapters for s in ch.scenes)
    setups = [s for s in novel.plot_state.setups if s.resolved_in is None]
    body = Text()
    body.append(f"《{novel.title}》\n", style=f"bold {TEXT}")
    body.append(f"{len(novel.chapters)} 章  ·  约 {chars} 字\n", style=MUTED)
    body.append(
        f"{len(novel.plot_state.characters)} 角色  ·  "
        f"{len(novel.plot_state.events)} 事件  ·  {len(setups)} 未回收伏笔",
        style=MUTED,
    )
    return Panel(
        body,
        box=box.ROUNDED,
        border_style=SUCCESS,
        title=f"[{SUCCESS}]done 成书[/]",
        title_align="left",
        padding=(0, 1),
        expand=False,
    )


# Rich treats a hex value as a style string.  Keeping this alias local makes
# the card construction above easier to scan.
SUBTLE_COLOR = "#303842"
