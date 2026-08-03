"""Shared fixtures for UI tests."""

from dataclasses import replace
from io import StringIO

import pytest
from rich.console import Console

from opennovel.config import Settings
from opennovel.llm import FakeProvider
from opennovel.ui.chat import ChatStream
from opennovel.ui.repl import Session


@pytest.fixture
def make_session(tmp_path):
    def _make(provider: FakeProvider = None, **overrides) -> Session:
        provider = provider or FakeProvider()
        settings = replace(
            Settings(), output_dir=tmp_path, max_chapters=1, chapter_target_chars=200
        )
        if overrides:
            settings = replace(settings, **overrides)
        console = Console(file=StringIO(), force_terminal=False, width=100)
        return Session(provider=provider, settings=settings, console=console, chat=ChatStream(console))

    return _make
