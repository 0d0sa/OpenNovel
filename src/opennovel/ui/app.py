"""Full-screen chat application (Claude Code / Codex style).

Layout: a scrollable chat history window on top, a fixed input box at the
bottom. Rich renderables are bridged to the history via ANSI text. Commands
run in a single background worker thread; the input box is read-only while
a command is running.
"""

from __future__ import annotations

import threading

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl, Point, UIContent
from prompt_toolkit.layout.dimension import Dimension

from opennovel.config import Settings
from opennovel.llm import Provider
from opennovel.ui import display
from opennovel.ui.chat import ChatView
from opennovel.ui.input import CommandCompleter
from opennovel.ui.repl import Session, handle_command


class CenteredInputControl(BufferControl):
    """BufferControl that vertically centers its content in the window.

    The input window has a fixed height; when the buffer wraps to fewer lines
    than the window, the text is centered instead of top-aligned.
    """

    def create_content(self, width, height, preview_search=False):
        content = super().create_content(width, height, preview_search)
        n = content.line_count
        if n >= height or height <= 0:
            return content
        top = (height - n) // 2
        cursor = content.cursor_position
        padded_cursor = Point(cursor.x, cursor.y + top) if cursor else None
        return UIContent(
            get_line=lambda i: content.get_line(i - top) if top <= i < top + n else [],
            line_count=height,
            cursor_position=padded_cursor,
            menu_position=content.menu_position,
            show_cursor=content.show_cursor,
        )


class FullScreenChatApp:
    """Runs the chat session in a full-screen terminal application."""

    def __init__(self, provider: Provider, settings: Settings):
        self.settings = settings
        self.view = ChatView()
        self.session = Session(provider=provider, settings=settings, console=None, chat=self.view)
        self.session.show_status = self._system_view(
            lambda: display.status_view(self.session.novel)
            if self.session.novel
            else _yellow("尚未开始任何书，先用 /new 开始")
        )
        self.session.show_style = self._system_view(
            lambda: display.style_panel(self.session.novel.style_profile)
            if self.session.novel
            else _yellow("尚未开始任何书，先用 /new 开始")
        )
        self.session.show_checks = self._system_view(
            lambda: display.checks_group(self.session.novel)
        )
        self.session.show_help = self._system_view(lambda: display.help_table())
        self.session.say = lambda text: self._add_system_text(text)
        self.session.ask = self._ask
        self._busy = False
        self._pending_ask: dict | None = None

        self.buffer = Buffer(
            multiline=True,
            completer=CommandCompleter(),
            accept_handler=self._on_accept,
        )
        self.header_window = Window(
            content=FormattedTextControl(
                lambda: self._header_text(provider.model),
                style="bold cyan",
            ),
            height=1,
            always_hide_cursor=True,
        )
        self.history_window = Window(
            content=FormattedTextControl(self._history_text),
            wrap_lines=True,
            always_hide_cursor=True,
        )
        self.top_line = _divider()
        self.input_window = Window(
            content=CenteredInputControl(buffer=self.buffer, focus_on_click=True),
            height=Dimension(min=1, max=2),
            wrap_lines=True,
        )
        self.bottom_line = _divider()
        self.layout = Layout(
            HSplit(
                [
                    self.header_window,
                    self.history_window,
                    self.top_line,
                    self.input_window,
                    self.bottom_line,
                ]
            ),
            focused_element=self.input_window,
        )

        kb = KeyBindings()

        @kb.add("enter", eager=True)
        @kb.add("c-j", eager=True)
        def _submit(event):
            self.buffer.validate_and_handle()

        @kb.add("escape", "enter", filter=True)
        def _newline(event):
            event.current_buffer.insert_text("\n")

        @kb.add("c-c", eager=True)
        def _interrupt(event):
            event.app.exit(exception=KeyboardInterrupt())

        self.app = Application(
            layout=self.layout,
            key_bindings=kb,
            full_screen=True,
            mouse_support=False,
        )

    # --- history / input plumbing ---

    @staticmethod
    def _header_text(model: str) -> str:
        text = " OpenNovel — 小说写作 Agent"
        if model:
            text += f"  [模型: {model}]"
        return text

    def _history_text(self):
        return ANSI(self.view.ansi_text)

    def _system_view(self, make):
        def show():
            self._add_system_renderable(make())

        return show

    def _add_system_text(self, text: str) -> None:
        from rich.text import Text

        self.view.add_system(Text.from_markup(text))
        self._invalidate()

    def _add_system_renderable(self, renderable) -> None:
        if renderable is None:
            return
        self.view.add_system(renderable)
        self._invalidate()

    def _exit_app(self) -> None:
        """Exit the app; safe to call when the event loop is not running."""
        try:
            self.app.exit()
        except Exception:
            pass

    def _invalidate(self) -> None:
        if not self.app:
            return
        # auto-follow the bottom of the chat history
        lines = self.view.ansi_text.count("\n")
        self.history_window.vertical_scroll = lines
        self.app.invalidate()

    def _ask(self, prompt: str) -> str:
        """Full-screen ask: show the question in chat, wait for an answer."""
        from rich.text import Text

        event = threading.Event()
        holder = {"event": event, "value": ""}
        self._pending_ask = holder
        self.view.add_system(Text(f"【{prompt}】", style="bold yellow"))
        self._invalidate()
        event.wait()
        value = holder["value"]
        return value

    def _on_accept(self, buffer: Buffer) -> None:
        if self._busy:
            return
        text = buffer.text.strip()
        if not text:
            return
        buffer.text = ""
        if self._pending_ask is not None:
            if text == "/help":
                self.view.add_system(display.help_table())
                self._invalidate()
                return
            holder = self._pending_ask
            self.view.add_user(text)
            if text == "/exit":
                holder["value"] = ""
                holder["event"].set()
                self._pending_ask = None
                self._exit_app()
                return
            self._pending_ask = None
            holder["value"] = text
            holder["event"].set()
            return
        self.view.add_user(text)
        self._invalidate()
        self._run(text)

    def _run(self, text: str) -> None:
        if self._busy:
            return
        self._busy = True
        self._invalidate()

        def worker():
            try:
                keep = handle_command(self.session, text)
                if not keep or self.session.exiting:
                    self._exit_app()
            except Exception as exc:
                self.view.add_system(display.Text(f"错误：{exc}", style="red"))
                self._invalidate()
            finally:
                self._busy = False
                self._invalidate()

        threading.Thread(target=worker, daemon=True).start()

    def run(self) -> int:
        self.view.add_system(display.banner_text())
        self.view.add_system(display.help_table())
        self._invalidate()
        try:
            self.app.run()
        except KeyboardInterrupt:
            pass
        return 0


def _yellow(text: str):
    from rich.text import Text

    return Text(text, style="yellow")


def _divider() -> Window:
    """A 1-line horizontal separator drawn across the terminal width."""
    from prompt_toolkit.formatted_text import FormattedText

    def content():
        return FormattedText([("class:divider", "─" * 400)])

    return Window(content=FormattedTextControl(content), height=1)
