"""Full-screen chat application with a Codex/Claude-inspired terminal UI.

Layout: compact project header, scrollable transcript, and a fixed composer
with keyboard hints and live session state. Rich renderables are bridged to
the transcript via ANSI text. Commands run in one background worker thread;
the composer stays writable only when idle or when a command is asking the
user a question.
"""

from __future__ import annotations

import threading

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Float, FloatContainer, HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl, Point, UIContent
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.layout.processors import BeforeInput

from opennovel.config import Settings
from opennovel.llm import Provider
from opennovel.ui import display
from opennovel.ui.chat import ChatView
from opennovel.ui.input import CommandCompleter
from opennovel.ui.repl import Session, handle_command
from opennovel.ui.theme import UI_STYLE


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

    def __init__(self, provider: Provider, settings: Settings, *, output=None):
        self.settings = settings
        self.model = provider.model
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
            history=InMemoryHistory(),
            complete_while_typing=True,
            read_only=Condition(lambda: self._busy and self._pending_ask is None),
            accept_handler=self._on_accept,
        )
        self.header_window = Window(
            content=FormattedTextControl(self._header_fragments),
            height=2,
            style="class:header",
            always_hide_cursor=True,
        )
        self.history_window = Window(
            content=FormattedTextControl(self._history_text),
            wrap_lines=True,
            style="class:history",
            right_margins=[ScrollbarMargin(display_arrows=False)],
            always_hide_cursor=True,
        )
        self.top_line = Window(
            content=FormattedTextControl(self._composer_rule),
            height=1,
            always_hide_cursor=True,
        )
        self.input_window = Window(
            content=CenteredInputControl(
                buffer=self.buffer,
                focus_on_click=True,
                input_processors=[BeforeInput("> ", style="class:composer.prompt")],
            ),
            height=Dimension(min=1, max=5, preferred=2),
            wrap_lines=True,
            style="class:composer.input",
        )
        self.footer_window = Window(
            content=FormattedTextControl(self._footer_fragments),
            height=1,
            style="class:footer",
            always_hide_cursor=True,
        )
        self.body = HSplit(
            [
                self.header_window,
                self.history_window,
                self.top_line,
                self.input_window,
                self.footer_window,
            ],
            style="class:root",
        )
        self.root = FloatContainer(
            content=self.body,
            floats=[
                Float(
                    xcursor=True,
                    ycursor=True,
                    content=CompletionsMenu(max_height=8, scroll_offset=1),
                )
            ],
        )
        self.layout = Layout(
            self.root,
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

        @kb.add("pageup", eager=True)
        def _page_up(event):
            amount = (
                max(3, self.history_window.render_info.window_height // 2)
                if self.history_window.render_info
                else 10
            )
            self.history_window.vertical_scroll = max(0, self.history_window.vertical_scroll - amount)
            event.app.invalidate()

        @kb.add("pagedown", eager=True)
        def _page_down(event):
            amount = (
                max(3, self.history_window.render_info.window_height // 2)
                if self.history_window.render_info
                else 10
            )
            self.history_window.vertical_scroll += amount
            event.app.invalidate()

        self.app = Application(
            layout=self.layout,
            key_bindings=kb,
            style=UI_STYLE,
            full_screen=True,
            mouse_support=False,
            output=output,
        )

    # --- history / input plumbing ---

    @staticmethod
    def _header_text(model: str) -> str:
        text = "OpenNovel — 小说写作 Agent"
        if model:
            text += f"  ·  {model}"
        return text

    def _header_fragments(self):
        book = self.session.title or "未打开作品"
        state_style, state_label = self._state_label()
        fragments = [
            ("class:header.brand", "  OpenNovel"),
            ("class:header.meta", "  /  "),
            ("class:header.title", "小说写作智能体"),
            ("", "\n"),
            ("class:header.meta", f"  {book}  ·  {self.model or '未配置模型'}  ·  "),
            (state_style, state_label),
        ]
        return FormattedText(fragments)

    def _state_label(self) -> tuple[str, str]:
        if self._pending_ask is not None:
            return "class:status.ask", "等待回答"
        if self._busy:
            return "class:status.busy", "正在生成"
        return "class:status.ready", "就绪"

    def _composer_rule(self):
        label = "回答问题" if self._pending_ask is not None else "输入消息"
        return FormattedText(
            [
                ("class:composer.rule", "── "),
                ("class:composer.label", label),
                ("class:composer.rule", " " + "─" * 400),
            ]
        )

    def _footer_fragments(self):
        state_style, state_label = self._state_label()
        if self._busy and self._pending_ask is None:
            return FormattedText(
                [
                    (state_style, f"  * {state_label}"),
                    ("class:footer", "  ·  完成前输入暂时锁定"),
                ]
            )
        return FormattedText(
            [
                ("class:footer.key", "  enter"),
                ("class:footer", " 发送   "),
                ("class:footer.key", "alt+enter"),
                ("class:footer", " 换行   "),
                ("class:footer.key", "/"),
                ("class:footer", " 命令   "),
                ("class:footer.key", "pgup/pgdn"),
                ("class:footer", " 滚动   ·   "),
                (state_style, f"* {state_label}"),
            ]
        )

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
        question = Text()
        question.append("- ", style="bold #7aa2f7")
        question.append(prompt, style="bold #d7dde5")
        self.view.add_system(question)
        self._invalidate()
        event.wait()
        value = holder["value"]
        return value

    def _on_accept(self, buffer: Buffer) -> None:
        # A background command can be busy *because it is waiting for this
        # answer*. Process pending questions before applying the busy guard.
        if self._busy and self._pending_ask is None:
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
                self.view.add_system(display.error_text(f"错误：{exc}"))
                self._invalidate()
            finally:
                self._busy = False
                self._invalidate()

        threading.Thread(target=worker, daemon=True).start()

    def run(self) -> int:
        self.view.add_system(display.welcome_panel(self.model))
        self._invalidate()
        try:
            self.app.run()
        except KeyboardInterrupt:
            pass
        return 0


def _yellow(text: str):
    from rich.text import Text

    return Text(text, style="yellow")
