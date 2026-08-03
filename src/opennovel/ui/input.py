"""prompt_toolkit input widget: multiline, history, `/` completion.

Enter submits, Shift+Enter inserts a newline (Claude Code style).
"""

from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings

from opennovel.ui.theme import UI_STYLE

COMMANDS = [
    ("new", "开始一本新书（书名 / 剧情 / 风格）"),
    ("write", "写作当前这本书"),
    ("status", "当前书概览"),
    ("style", "查看风格锚点"),
    ("checks", "查看各章检查报告"),
    ("rewrite", "手动重写某章，如 /rewrite 2"),
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


def _bindings() -> KeyBindings:
    kb = KeyBindings()

    @kb.add("enter", filter=True, eager=True)
    def _submit(event):
        event.current_buffer.validate_and_handle()

    @kb.add("c-j", filter=True, eager=True)
    def _submit_lf(event):
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
