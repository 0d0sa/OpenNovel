"""Tests for chat UI: agent-loop free text, chat stream, input completion."""

from io import StringIO

from prompt_toolkit.document import Document
from rich.console import Console

from opennovel.llm import FakeProvider
from opennovel.models import Chapter, Novel, Scene, SceneStatus
from opennovel.ui.chat import ChatStream
from opennovel.ui.input import CommandCompleter
from opennovel.ui.repl import handle_command


def text_turn(content: str) -> str:
    return FakeProvider.json_reply({"type": "text", "content": content})


def tool_turn(tool_name: str, arguments: dict, content: str = "") -> str:
    return FakeProvider.json_reply(
        {
            "type": "tool_call",
            "content": content,
            "tool_call": {"tool": tool_name, "arguments": arguments},
        }
    )


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


def test_free_text_routes_rewrite_tool(make_session):
    provider = FakeProvider(
        replies=[
            tool_turn("rewrite_chapter", {"chapter_no": 1}, "我来重写第一章"),
            "重写后的正文",
            text_turn("已重写完成"),
        ]
    )
    session = make_session(provider)
    session.title = "雾中城"
    session.plot = "剧情"
    session.novel = Novel(
        title="雾中城",
        plot="剧情",
        chapters=[
            Chapter(
                title="夜雨",
                scenes=[Scene(summary="s", content="旧正文", status=SceneStatus.WRITTEN)],
            )
        ],
    )
    handle_command(session, "把第一章重写得更紧张")
    assert session.novel.chapters[0].scenes[0].content == "重写后的正文"
    assert "已重写完成" in session.console.file.getvalue()


def test_free_text_routes_status_tool(make_session):
    provider = FakeProvider(
        replies=[tool_turn("read_status", {}), text_turn("进度如上。")]
    )
    session = make_session(provider)
    session.title = "雾中城"
    session.novel = Novel(title="雾中城", plot="剧情", chapters=[Chapter(title="夜雨")])
    handle_command(session, "现在写到哪了")
    out = session.console.file.getvalue()
    assert "夜雨" in out
    assert "进度如上" in out


def test_free_text_chat_reply_when_no_book(make_session):
    provider = FakeProvider(replies=[text_turn("还没有书，先 /new 创建，或直接告诉我书名和剧情。")])
    session = make_session(provider)
    handle_command(session, "加一段剧情")
    assert "先 /new" in session.console.file.getvalue()
