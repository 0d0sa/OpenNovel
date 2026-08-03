"""Tests for chat UI: intent routing, chat stream, input completion."""

from io import StringIO

from prompt_toolkit.document import Document
from rich.console import Console

from opennovel.agent import IntentKind, classify_intent
from opennovel.llm import FakeProvider
from opennovel.models import Chapter, Novel, Scene, SceneStatus
from opennovel.ui.chat import ChatStream
from opennovel.ui.input import CommandCompleter
from opennovel.ui.repl import handle_command


def intent_reply(kind: str, chapter_no: int = 0, suggestion: str = "") -> str:
    return FakeProvider.json_reply(
        {"kind": kind, "chapter_no": chapter_no, "suggestion": suggestion}
    )


def test_classify_start_new():
    provider = FakeProvider(replies=[intent_reply("start_new")])
    intent = classify_intent(provider, "帮我开一本新书，叫雾中城")
    assert intent.kind == IntentKind.START_NEW


def test_classify_rewrite_with_chapter():
    provider = FakeProvider(replies=[intent_reply("rewrite_chapter", chapter_no=2)])
    intent = classify_intent(provider, "把第二章重写得更紧张")
    assert intent.kind == IntentKind.REWRITE_CHAPTER
    assert intent.chapter_no == 2


def test_classify_fallback_to_append_on_failure():
    provider = FakeProvider()  # no replies -> structured parse fails
    intent = classify_intent(provider, "随便什么话")
    assert intent.kind == IntentKind.APPEND_PLOT


def test_classify_all_kinds():
    for kind in IntentKind:
        provider = FakeProvider(replies=[intent_reply(kind.value)])
        intent = classify_intent(provider, "x")
        assert intent.kind == kind


def test_chat_stream_echoes_and_streams():
    console = Console(file=StringIO(), force_terminal=False, width=80)
    chat = ChatStream(console)
    chat.add_user("你好")
    chat.add_assistant("你好呀")
    text = chat.stream_assistant(iter(["一二", "三"]))
    assert text == "一二三"
    chat.begin_stream()
    chat.feed("甲")
    chat.feed("乙")
    chat.end_stream()
    roles = [r for r, _ in chat.messages]
    assert roles == ["user", "assistant", "assistant", "assistant"]
    assert chat.messages[-1][1] == "甲乙"
    out = console.file.getvalue()
    assert "> 你好" in out
    assert "* OpenNovel" in out
    assert "一二三" in out


def test_chapter_card_content():
    console = Console(file=StringIO(), force_terminal=False, width=80)
    novel = Novel(
        title="雾中城",
        chapters=[Chapter(title="夜雨", scenes=[Scene(summary="s", content="正文", status=SceneStatus.WRITTEN)])],
    )
    card = ChatStream.chapter_card(novel, 1)
    with console.capture() as cap:
        console.print(card)
    assert "夜雨" in cap.get()


def test_completer_filters_commands():
    completer = CommandCompleter()
    doc = Document(text="/w")
    names = [c.text for c in completer.get_completions(doc, None)]
    assert "/write" in names
    assert "/new" not in names


def test_completer_ignores_non_slash():
    completer = CommandCompleter()
    doc = Document(text="hello")
    assert list(completer.get_completions(doc, None)) == []


def test_chat_input_bindings_construct():
    from opennovel.ui.input import _bindings

    kb = _bindings()
    names = {tuple(k.value if hasattr(k, "value") else k for k in b.keys) for b in kb.bindings}
    assert ("c-m",) in names  # enter submits
    assert ("c-j",) in names  # LF enter submits
    assert ("escape", "c-m") in names  # Meta+Enter newline


def test_free_text_routes_rewrite_intent(make_session, tmp_path):
    from opennovel.memory import PlotConsistency, StyleDeviation

    provider = FakeProvider(replies=[intent_reply("rewrite_chapter", chapter_no=1), "重写后的正文"])
    session = make_session(provider)
    session.novel = Novel(
        title="雾中城",
        chapters=[
            Chapter(
                title="夜雨",
                scenes=[Scene(summary="s", content="旧正文", status=SceneStatus.WRITTEN)],
                style_report=StyleDeviation(score=2, deviations=[], suggestion=""),
            )
        ],
    )
    handle_command(session, "把第一章重写得更紧张")
    assert session.novel.chapters[0].scenes[0].content == "重写后的正文"


def test_free_text_routes_status_intent(make_session):
    provider = FakeProvider(replies=[intent_reply("status")])
    session = make_session(provider)
    session.novel = Novel(title="雾中城", chapters=[Chapter(title="夜雨")])
    handle_command(session, "现在写到哪了")
    assert "夜雨" in session.console.file.getvalue()
    assert "已追加到剧情" not in session.console.file.getvalue()


def test_free_text_append_when_no_book(make_session):
    provider = FakeProvider(replies=[intent_reply("append_plot")])
    session = make_session(provider)
    handle_command(session, "加一段剧情")
    assert "先 /new" in session.console.file.getvalue()
