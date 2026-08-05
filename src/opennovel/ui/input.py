"""prompt_toolkit input widget: multiline, history, `/` completion.

Enter submits, Shift+Enter inserts a newline (Claude Code style).
"""

from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.menus import CompletionsMenu, CompletionsMenuControl

from opennovel.ui.theme import UI_STYLE

COMMANDS = [
    ("new", "开始一本新书（书名 / 剧情 / 风格）"),
    ("write", "连续写作 N 章，如 /write 2（默认 1 章）"),
    ("status", "当前书概览"),
    ("style", "查看风格锚点"),
    ("checks", "查看各章检查报告"),
    ("rewrite", "手动重写某章，如 /rewrite 2"),
    ("setting", "配置模型与生成参数"),
    ("model", "切换已配置的模型"),
    ("help", "显示帮助"),
    ("exit", "退出"),
]

PROMPT = "> "


class CommandCompleter(Completer):
    """Completes `/command` names."""

    def get_completions(self, document, complete_event):
        word = document.get_word_before_cursor(WORD=True)
        if not word.startswith("/"):
            return
        prefix = word[1:]
        for name, desc in COMMANDS:
            if name.startswith(prefix):
                yield Completion(f"/{name}", start_position=-len(word), display_meta=desc)


class FirstSelectedCompletionsMenuControl(CompletionsMenuControl):
    """Render the first match as selected without inserting it into the buffer."""

    def create_content(self, width: int, height: int):
        state = get_app().current_buffer.complete_state
        if state and state.completions and state.complete_index is None:
            # CompletionsMenuControl only highlights complete_index. Temporarily
            # expose index 0 while it builds immutable UIContent; do not call
            # Buffer.go_to_completion(), which would modify the user's input.
            state.complete_index = 0
            try:
                return super().create_content(width, height)
            finally:
                state.complete_index = None
        return super().create_content(width, height)


class FirstSelectedCompletionsMenu(CompletionsMenu):
    """Completion menu whose passive/default selection is the first match."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.content.content = FirstSelectedCompletionsMenuControl()


def apply_selected_completion(buffer: Buffer) -> bool:
    """Insert the highlighted completion, defaulting to the first match."""
    state = buffer.complete_state
    if state is None or not state.completions:
        return False
    completion = state.current_completion or state.completions[0]
    buffer.apply_completion(completion)
    return True


def _bindings() -> KeyBindings:
    kb = KeyBindings()

    @kb.add("enter", filter=True, eager=True)
    def _submit(event):
        apply_selected_completion(event.current_buffer)
        event.current_buffer.validate_and_handle()

    @kb.add("c-j", filter=True, eager=True)
    def _submit_lf(event):
        apply_selected_completion(event.current_buffer)
        event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter", filter=True)
    def _newline(event):
        event.current_buffer.insert_text("\n")

    return kb


class ChatInput:
    """Reusable chat input with history preserved across turns."""

    def __init__(self):
        self.history = InMemoryHistory()
        self.session: PromptSession | None = None

    def prompt(self, message: str = PROMPT) -> str:
        if self.session is None:
            self.session = PromptSession(
                message=message,
                history=self.history,
                completer=CommandCompleter(),
                key_bindings=_bindings(),
                multiline=True,
                complete_while_typing=True,
                style=UI_STYLE,
            )
        text = self.session.prompt()
        return text.strip()
