"""Tests for the full-screen chat app components."""

from io import StringIO

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from opennovel.llm import FakeProvider
from opennovel.models import Chapter, Novel, Scene, SceneStatus
from opennovel.ui.chat import ChatView, render_ansi
from opennovel.ui.display import help_table, status_view
from opennovel.ui.repl import handle_command


def test_render_ansi_contains_text():
    table = Table(title="测试")
    table.add_column("列")
    table.add_row("值")
    out = render_ansi(table, width=80)
    assert "测试" in out
    assert "值" in out


def test_render_ansi_panel():
    out = render_ansi(Panel("正文内容", title="标题"), width=80)
    assert "正文内容" in out
    assert "标题" in out


def test_chat_view_appends_and_streams():
    view = ChatView(width=80)
    view.add_user("你好")
    view.add_system(Text("系统消息", style="red"))
    assert "你好" in view.ansi_text
    assert "系统消息" in view.ansi_text
    assert view.messages == [("user", "你好"), ("system", "系统消息")]


def test_chat_view_stream_shows_partial_and_final():
    view = ChatView(width=80)
    view.begin_stream()
    view.feed("一")
    assert "一" in view.ansi_text
    view.feed("二")
    view.end_stream()
    assert "一二" in view.ansi_text
    assert view.messages[-1] == ("assistant", "一二")


def test_chat_view_static_cards():
    novel = Novel(
        title="雾中城",
        chapters=[
            Chapter(
                title="夜雨",
                scenes=[Scene(summary="s", content="正文", status=SceneStatus.WRITTEN)],
            )
        ],
    )
    console = Console(file=StringIO(), force_terminal=False, width=80)
    with console.capture() as cap:
        console.print(ChatView.chapter_card(novel, 1))
    assert "夜雨" in cap.get()


def test_display_renderables():
    rendered = render_ansi(help_table(), width=80)
    assert "命令" in rendered
    novel = Novel(title="雾中城", chapters=[Chapter(title="夜雨")])
    rendered = render_ansi(status_view(novel), width=80)
    assert "夜雨" in rendered


def test_fullscreen_accept_flow_with_pipe(tmp_path):
    """Drive the app's accept handler without a real terminal."""
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    provider = FakeProvider(replies=[FakeProvider.json_reply({"kind": "help", "chapter_no": 0, "suggestion": ""})])
    app = FullScreenChatApp(provider, Settings(output_dir=tmp_path, max_chapters=1))
    # bypass the real Application.run loop: exercise accept handler directly
    buffer = Buffer()
    buffer.text = "/help"
    app.buffer = buffer
    app._on_accept(buffer)
    assert buffer.text == ""  # consumed
    assert any(r == "system" for r, _ in app.view.messages)


def test_fullscreen_busy_ignores_input(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(FakeProvider(), Settings(output_dir=tmp_path))
    app._busy = True
    buffer = Buffer()
    buffer.text = "任何输入"
    app._on_accept(buffer)
    assert buffer.text == "任何输入"  # untouched while busy


def test_fullscreen_ask_flow(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(FakeProvider(), Settings(output_dir=tmp_path))
    holder = {"event": __import__("threading").Event(), "value": ""}
    app._pending_ask = holder

    buffer = Buffer()
    buffer.text = "雾中城"
    app._on_accept(buffer)
    assert holder["value"] == "雾中城"
    assert buffer.text == ""


def test_fullscreen_exit_during_ask(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(FakeProvider(), Settings(output_dir=tmp_path))
    holder = {"event": __import__("threading").Event(), "value": ""}
    app._pending_ask = holder

    buffer = Buffer()
    buffer.text = "/exit"
    app._on_accept(buffer)
    assert holder["value"] == ""
    assert app._pending_ask is None


def test_fullscreen_system_text_renders_markup(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(FakeProvider(), Settings(output_dir=tmp_path))
    app._add_system_text("[yellow]还没有开始新书[/yellow]")
    assert "[yellow]" not in app.view.ansi_text
    assert "还没有开始新书" in app.view.ansi_text


def test_chat_view_escapes_user_markup():
    view = ChatView(width=80)
    view.add_user("你好[dim]世界")
    # markup must render literally (no dim SGR escape applied)
    assert "\x1b[2m" not in view.ansi_text
    assert "你好" in view.ansi_text
    assert view.messages[0][1] == "你好[dim]世界"


def test_route_other_strips_llm_markup(make_session):
    from opennovel.agent import IntentKind
    from opennovel.llm import FakeProvider

    provider = FakeProvider(
        replies=[FakeProvider.json_reply({"kind": "other", "chapter_no": 0, "suggestion": "[dim]（您好！）[/dim]"})]
    )
    session = make_session(provider)
    session.title, session.plot = "雾中城", "剧情"
    handle_command(session, "你好")
    out = session.console.file.getvalue()
    assert "[dim]" not in out
    assert "（您好！）" in out
