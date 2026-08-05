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
from prompt_toolkit.layout.containers import (
    DynamicContainer,
    HSplit,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl, Point, UIContent
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.layout.processors import BeforeInput, ConditionalProcessor, PasswordProcessor

from opennovel.config import Settings
from opennovel.llm import Provider
from opennovel.ui import display
from opennovel.ui.chat import ChatView
from opennovel.ui.input import (
    CommandCompleter,
    FirstSelectedCompletionsMenu,
    apply_selected_completion,
)
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

    def __init__(
        self, provider: Provider, settings: Settings, *, output=None, settings_path=None
    ):
        self.settings = settings
        self.model = provider.model
        self.view = ChatView()
        self.session = Session(
            provider=provider,
            settings=settings,
            console=None,
            chat=self.view,
            settings_path=settings_path,
        )
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
        self.session.on_provider_change = self._refresh_header
        self._busy = False
        self._pending_ask: dict | None = None
        self._settings_open = False
        self._settings_error = ""

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
            content=FormattedTextControl(
                self._history_text,
                # A non-focusable FormattedTextControl otherwise keeps its
                # implicit cursor at the first line, so appended prompts can
                # remain below the visible viewport. Put the hidden cursor at
                # the end to make the history reliably follow new output.
                get_cursor_position=self._history_cursor_position,
            ),
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
                input_processors=[
                    ConditionalProcessor(
                        processor=PasswordProcessor(char="•"),
                        filter=Condition(self._is_secret_prompt),
                    ),
                    # Add the prompt after password masking so `> ` remains
                    # visible while only the secret value becomes bullets.
                    BeforeInput("> ", style="class:composer.prompt"),
                ],
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
        # Keep completion matches in normal layout flow. A cursor-anchored
        # Float is automatically flipped by prompt_toolkit when the composer
        # is near the bottom, which can place the menu at the top of the app.
        self.completions_menu = FirstSelectedCompletionsMenu(
            max_height=8, scroll_offset=1
        )
        self.body = HSplit(
            [
                self.header_window,
                self.history_window,
                self.completions_menu,
                self.top_line,
                self.input_window,
                self.footer_window,
            ],
            style="class:root",
        )
        self.chat_root = self.body
        self._build_settings_screen()
        self.root = DynamicContainer(
            lambda: self.settings_root if self._settings_open else self.chat_root
        )
        self.layout = Layout(
            self.root,
            focused_element=self.input_window,
        )

        kb = KeyBindings()
        in_chat = Condition(lambda: not self._settings_open)
        in_settings = Condition(lambda: self._settings_open)

        @kb.add("enter", eager=True, filter=in_chat)
        @kb.add("c-j", eager=True, filter=in_chat)
        def _submit(event):
            apply_selected_completion(self.buffer)
            self.buffer.validate_and_handle()

        @kb.add("escape", "enter", filter=in_chat)
        def _newline(event):
            event.current_buffer.insert_text("\n")

        @kb.add("c-c", eager=True)
        def _interrupt(event):
            if self._settings_open:
                self._close_settings_screen()
            else:
                event.app.exit(exception=KeyboardInterrupt())

        @kb.add("pageup", eager=True, filter=in_chat)
        def _page_up(event):
            amount = (
                max(3, self.history_window.render_info.window_height // 2)
                if self.history_window.render_info
                else 10
            )
            self.history_window.vertical_scroll = max(0, self.history_window.vertical_scroll - amount)
            event.app.invalidate()

        @kb.add("pagedown", eager=True, filter=in_chat)
        def _page_down(event):
            amount = (
                max(3, self.history_window.render_info.window_height // 2)
                if self.history_window.render_info
                else 10
            )
            self.history_window.vertical_scroll += amount
            event.app.invalidate()

        @kb.add("tab", eager=True, filter=in_settings)
        def _settings_next(event):
            self._focus_settings_field(event, 1)

        @kb.add("s-tab", eager=True, filter=in_settings)
        def _settings_previous(event):
            self._focus_settings_field(event, -1)

        @kb.add("enter", eager=True, filter=in_settings)
        @kb.add("c-j", eager=True, filter=in_settings)
        def _settings_enter(event):
            if event.current_buffer is self.setting_plot_check_buffer:
                self._save_settings_form()
            else:
                self._focus_settings_field(event, 1)

        @kb.add("c-s", eager=True, filter=in_settings)
        def _settings_save(event):
            self._save_settings_form()

        @kb.add("escape", eager=True, filter=in_settings)
        def _settings_cancel(event):
            self._close_settings_screen()

        self.app = Application(
            layout=self.layout,
            key_bindings=kb,
            style=UI_STYLE,
            full_screen=True,
            mouse_support=False,
            output=output,
        )

    # --- settings screen ---

    def _build_settings_screen(self) -> None:
        """Build the dedicated `/setting` form shown in place of chat."""
        self.setting_name_buffer = Buffer(multiline=False)
        self.setting_base_url_buffer = Buffer(multiline=False)
        self.setting_api_key_buffer = Buffer(multiline=False)
        self.setting_model_buffer = Buffer(multiline=False)
        self.setting_temperature_buffer = Buffer(multiline=False)
        self.setting_max_tokens_buffer = Buffer(multiline=False)
        self.setting_interval_buffer = Buffer(multiline=False)
        self.setting_language_buffer = Buffer(multiline=False)
        self.setting_chapter_chars_buffer = Buffer(multiline=False)
        self.setting_max_chapters_buffer = Buffer(multiline=False)
        self.setting_output_dir_buffer = Buffer(multiline=False)
        self.setting_style_check_buffer = Buffer(multiline=False)
        self.setting_plot_check_buffer = Buffer(multiline=False)
        self._settings_buffers = [
            self.setting_name_buffer,
            self.setting_base_url_buffer,
            self.setting_api_key_buffer,
            self.setting_model_buffer,
            self.setting_temperature_buffer,
            self.setting_max_tokens_buffer,
            self.setting_interval_buffer,
            self.setting_language_buffer,
            self.setting_chapter_chars_buffer,
            self.setting_max_chapters_buffer,
            self.setting_output_dir_buffer,
            self.setting_style_check_buffer,
            self.setting_plot_check_buffer,
        ]

        fields = [
            self._settings_field(
                "配置名 / Profile name",
                self.setting_name_buffer,
                "例如 deepseek、qwen、openai",
            ),
            self._settings_field(
                "服务地址 / Base URL",
                self.setting_base_url_buffer,
                "留空使用 OpenAI 官方地址",
            ),
            self._settings_field(
                "API key",
                self.setting_api_key_buffer,
                "编辑已有配置时留空可保留原密钥",
                secret=True,
            ),
            self._settings_field(
                "模型 / Model",
                self.setting_model_buffer,
                "例如 deepseek-chat、qwen-plus、gpt-5",
            ),
            self._settings_field(
                "采样温度 / Temperature",
                self.setting_temperature_buffer,
                "0.0–2.0，默认 0.7",
            ),
            self._settings_field(
                "最大 token / Max tokens",
                self.setting_max_tokens_buffer,
                "单次调用上限，默认 4096",
            ),
            self._settings_field(
                "调用间隔 / Interval",
                self.setting_interval_buffer,
                "低 RPM 服务可增加秒数，默认 0",
            ),
            self._settings_field(
                "成书语言 / Language",
                self.setting_language_buffer,
                "例如 zh、en",
            ),
            self._settings_field(
                "每章目标字数 / Chapter chars",
                self.setting_chapter_chars_buffer,
                "默认 3000",
            ),
            self._settings_field(
                "最大章节数 / Max chapters",
                self.setting_max_chapters_buffer,
                "默认 20",
            ),
            self._settings_field(
                "输出目录 / Output directory",
                self.setting_output_dir_buffer,
                "默认 novels",
            ),
            self._settings_field(
                "风格检查 / Style check",
                self.setting_style_check_buffer,
                "on 或 off",
            ),
            self._settings_field(
                "剧情检查 / Plot check",
                self.setting_plot_check_buffer,
                "on 或 off",
            ),
        ]
        form = VSplit(
            [
                HSplit(fields[:7]),
                Window(width=1, char="│", style="class:settings.hint"),
                HSplit(fields[7:]),
            ]
        )
        self.settings_root = HSplit(
            [
                Window(
                    content=FormattedTextControl(self._settings_header_fragments),
                    height=2,
                    style="class:settings.header",
                    always_hide_cursor=True,
                ),
                Window(height=1),
                Window(
                    content=FormattedTextControl(self._settings_intro_fragments),
                    height=4,
                    always_hide_cursor=True,
                ),
                Window(
                    content=FormattedTextControl(self._settings_profiles_fragments),
                    height=Dimension(min=2, max=5, preferred=3),
                    wrap_lines=True,
                    always_hide_cursor=True,
                ),
                form,
                Window(
                    content=FormattedTextControl(self._settings_error_fragments),
                    height=1,
                    always_hide_cursor=True,
                ),
                Window(
                    content=FormattedTextControl(self._settings_footer_fragments),
                    height=1,
                    style="class:settings.footer",
                    always_hide_cursor=True,
                ),
            ],
            style="class:settings.root",
        )

    def _settings_field(
        self, label: str, buffer: Buffer, hint: str, *, secret: bool = False
    ) -> HSplit:
        processors = []
        if secret:
            processors.append(PasswordProcessor(char="•"))
        processors.append(BeforeInput("  › ", style="class:settings.prompt"))
        return HSplit(
            [
                Window(
                    content=FormattedTextControl(
                        [
                            ("class:settings.label", f"  {label}"),
                            ("class:settings.hint", f"   {hint}"),
                        ]
                    ),
                    height=1,
                    always_hide_cursor=True,
                ),
                Window(
                    content=BufferControl(
                        buffer=buffer,
                        focus_on_click=True,
                        input_processors=processors,
                    ),
                    height=1,
                    style="class:settings.input",
                ),
            ]
        )

    def _settings_header_fragments(self):
        return FormattedText(
            [
                ("class:settings.brand", "  OpenNovel"),
                ("class:settings.meta", "  /  设置"),
                ("", "\n"),
                ("class:settings.meta", "  Agent 配置  ·  "),
                (
                    "class:settings.active",
                    self.model or "尚未配置模型",
                ),
            ]
        )

    @staticmethod
    def _settings_intro_fragments():
        return FormattedText(
            [
                ("class:settings.title", "  配置模型与生成参数\n"),
                (
                    "class:settings.hint",
                    "  模型与生成参数统一保存在本地；保存后立即在当前会话生效。\n\n",
                ),
                ("class:settings.label", "  已保存的配置"),
            ]
        )

    def _settings_profiles_fragments(self):
        user_settings = self.session.ensure_user_settings()
        if user_settings is None or not user_settings.profiles:
            return FormattedText(
                [("class:settings.hint", "  暂无配置，这是你的第一个模型。")]
            )
        fragments = []
        for name, profile in user_settings.profiles.items():
            marker = "●" if name == user_settings.active else "○"
            style = (
                "class:settings.active"
                if name == user_settings.active
                else "class:settings.hint"
            )
            fragments.append((style, f"  {marker} {name}  ·  {profile.model}\n"))
        return FormattedText(fragments)

    def _settings_error_fragments(self):
        if not self._settings_error:
            return FormattedText([])
        return FormattedText(
            [("class:settings.error", f"  ! {self._settings_error}")]
        )

    @staticmethod
    def _settings_footer_fragments():
        return FormattedText(
            [
                ("class:settings.footer.key", "  tab / shift+tab"),
                ("class:settings.footer", " 切换   "),
                ("class:settings.footer.key", "enter"),
                ("class:settings.footer", " 下一项/保存   "),
                ("class:settings.footer.key", "ctrl+s"),
                ("class:settings.footer", " 保存   "),
                ("class:settings.footer.key", "esc"),
                ("class:settings.footer", " 返回"),
            ]
        )

    def _open_settings_screen(self) -> None:
        """Populate and display the standalone settings page."""
        from opennovel.config import runtime_from_settings

        self._settings_error = ""
        user_settings = self.session.ensure_user_settings()
        profile = user_settings.active_profile() if user_settings else None
        runtime = (
            user_settings.runtime
            if user_settings
            else runtime_from_settings(self.session.settings)
        )
        values = [
            profile.name if profile else "",
            (profile.base_url or "") if profile else "",
            "",
            profile.model if profile else "",
            str(runtime.temperature),
            str(runtime.max_tokens),
            str(runtime.call_interval),
            runtime.language,
            str(runtime.chapter_target_chars),
            str(runtime.max_chapters),
            runtime.output_dir,
            "on" if runtime.style_check else "off",
            "on" if runtime.plot_check else "off",
        ]
        for buffer, value in zip(self._settings_buffers, values):
            buffer.text = value
            buffer.cursor_position = len(value)
        self._settings_open = True
        self.app.layout.focus(self.setting_name_buffer)
        self.app.invalidate()

    def _close_settings_screen(self) -> None:
        self._settings_open = False
        self._settings_error = ""
        self.setting_api_key_buffer.text = ""
        self.app.layout.focus(self.input_window)
        self.app.invalidate()

    def _focus_settings_field(self, event, offset: int) -> None:
        try:
            index = self._settings_buffers.index(event.current_buffer)
        except ValueError:
            index = 0
        target = self._settings_buffers[(index + offset) % len(self._settings_buffers)]
        event.app.layout.focus(target)

    def _save_settings_form(self) -> None:
        from opennovel.config import runtime_from_settings
        from opennovel.settings_store import ProfileConfig
        from opennovel.ui.repl import _runtime_from_values

        name = self.setting_name_buffer.text.strip()
        base_url = self.setting_base_url_buffer.text.strip()
        api_key = self.setting_api_key_buffer.text.strip()
        model = self.setting_model_buffer.text.strip()
        if not name:
            self._settings_error = "配置名不能为空"
            self.app.layout.focus(self.setting_name_buffer)
            self.app.invalidate()
            return
        if not model:
            self._settings_error = "模型名不能为空"
            self.app.layout.focus(self.setting_model_buffer)
            self.app.invalidate()
            return

        user_settings = self.session.ensure_user_settings()
        existing = user_settings.profiles.get(name) if user_settings else None
        if not api_key and existing is not None:
            api_key = existing.api_key
        if not api_key:
            self._settings_error = "API key 不能为空"
            self.app.layout.focus(self.setting_api_key_buffer)
            self.app.invalidate()
            return

        current_runtime = (
            user_settings.runtime
            if user_settings
            else runtime_from_settings(self.session.settings)
        )
        runtime = _runtime_from_values(
            current_runtime,
            {
                "temperature": self.setting_temperature_buffer.text.strip(),
                "max_tokens": self.setting_max_tokens_buffer.text.strip(),
                "interval": self.setting_interval_buffer.text.strip(),
                "language": self.setting_language_buffer.text.strip(),
                "chapter_target_chars": self.setting_chapter_chars_buffer.text.strip(),
                "max_chapters": self.setting_max_chapters_buffer.text.strip(),
                "output_dir": self.setting_output_dir_buffer.text.strip(),
                "style_check": self.setting_style_check_buffer.text.strip(),
                "plot_check": self.setting_plot_check_buffer.text.strip(),
            },
        )
        if runtime is None:
            self._settings_error = "生成参数无效，请检查数字范围、目录和 on/off 开关"
            self.app.invalidate()
            return

        try:
            profile = ProfileConfig(
                name=name,
                base_url=base_url or None,
                api_key=api_key,
                model=model,
            )
            self.session.save_profile(profile, runtime)
        except Exception as exc:
            self._settings_error = f"保存失败：{exc}"
            self.app.invalidate()
            return

        self._close_settings_screen()
        self._add_system_text(
            f"[green]已保存并切换到 {profile.name}（{profile.model}）[/green]"
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

    def _history_cursor_position(self) -> Point:
        """Place the history's hidden cursor after its final rendered line."""
        return Point(x=0, y=self.view.ansi_text.count("\n"))

    def _is_secret_prompt(self) -> bool:
        return bool(self._pending_ask and self._pending_ask.get("secret"))

    def _refresh_header(self) -> None:
        """Called after the provider/model changes; repaint the status bar."""
        self.model = self.session.provider.model
        self._invalidate()

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

    def _ask(self, prompt: str, *, secret: bool = False) -> str:
        """Full-screen ask: show the question in chat, wait for an answer."""
        from rich.text import Text

        event = threading.Event()
        holder = {
            "event": event,
            "value": "",
            "secret": secret,
        }
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
        if self._pending_ask is not None:
            holder = self._pending_ask
            buffer.text = ""
            if text == "/help":
                self.view.add_system(display.help_table())
                self._invalidate()
                return
            if holder.get("secret"):
                self.view.add_user("••••••••")
            elif text:
                self.view.add_user(text)
            else:
                self.view.add_user("（留空）")
            if text == "/exit":
                holder["value"] = ""
                holder["event"].set()
                self._pending_ask = None
                self._exit_app()
                return
            self._pending_ask = None
            holder["value"] = text
            # Repaint the submitted answer immediately. The worker will add
            # the next prompt after it wakes, but it must not be responsible
            # for making this state transition visible.
            self._invalidate()
            holder["event"].set()
            return
        if not text:
            return
        buffer.text = ""
        self.view.add_user(text)
        if text.lower() == "/setting":
            self._open_settings_screen()
            return
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
