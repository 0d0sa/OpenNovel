"""Tests for the full-screen chat app components."""

from io import StringIO

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.output import DummyOutput
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from opennovel.llm import FakeProvider
from opennovel.models import Chapter, Novel, Scene, SceneStatus
from opennovel.ui.chat import ChatView, render_ansi
from opennovel.ui.display import help_table, status_view, welcome_panel
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
    rendered = render_ansi(welcome_panel("test-model"), width=80)
    assert "OpenNovel" in rendered
    assert "/new" in rendered
    assert "test-model" in rendered
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
    app = FullScreenChatApp(
        provider,
        Settings(output_dir=tmp_path, max_chapters=1),
        output=DummyOutput(),
    )
    # bypass the real Application.run loop: exercise accept handler directly
    buffer = Buffer()
    buffer.text = "/help"
    app.buffer = buffer
    app._on_accept(buffer)
    assert buffer.text == ""  # consumed
    assert any(r == "system" for r, _ in app.view.messages)


def test_fullscreen_setting_opens_dedicated_screen(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(
        FakeProvider(),
        Settings(output_dir=tmp_path),
        output=DummyOutput(),
        settings_path=tmp_path / "settings.json",
    )
    app.buffer.text = "/setting"
    app._on_accept(app.buffer)

    assert app._settings_open
    assert app.layout.current_buffer is app.setting_name_buffer
    assert app.setting_name_buffer.text == ""
    assert app.setting_api_key_buffer.text == ""
    assert app.view.messages[-1] == ("user", "/setting")


def test_fullscreen_setting_prefills_active_profile_without_key(tmp_path):
    from opennovel.config import Settings
    from opennovel.settings_store import ProfileConfig, UserSettings, save_user_settings
    from opennovel.ui.app import FullScreenChatApp

    path = tmp_path / "settings.json"
    profile = ProfileConfig(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-secret",
        model="deepseek-chat",
    )
    save_user_settings(
        UserSettings(active="deepseek", profiles={"deepseek": profile}), path
    )
    app = FullScreenChatApp(
        FakeProvider(), Settings(output_dir=tmp_path), output=DummyOutput(), settings_path=path
    )
    app._open_settings_screen()

    assert app.setting_name_buffer.text == "deepseek"
    assert app.setting_base_url_buffer.text == "https://api.deepseek.com/v1"
    assert app.setting_api_key_buffer.text == ""
    assert app.setting_model_buffer.text == "deepseek-chat"
    assert "sk-secret" not in str(app._settings_profiles_fragments())


def test_fullscreen_setting_saves_and_returns_to_chat(tmp_path, monkeypatch):
    from opennovel.config import Settings
    from opennovel.settings_store import load_user_settings
    from opennovel.ui.app import FullScreenChatApp

    path = tmp_path / "settings.json"
    monkeypatch.setattr(
        "opennovel.llm.build_provider_from_profile",
        lambda profile, settings: FakeProvider(model=profile.model),
    )
    app = FullScreenChatApp(
        FakeProvider(), Settings(output_dir=tmp_path), output=DummyOutput(), settings_path=path
    )
    app._open_settings_screen()
    app.setting_name_buffer.text = "qwen"
    app.setting_base_url_buffer.text = "https://example.test/v1"
    app.setting_api_key_buffer.text = "sk-new-secret"
    app.setting_model_buffer.text = "qwen-plus"
    app.setting_temperature_buffer.text = "0.4"
    app._save_settings_form()

    saved = load_user_settings(path)
    assert not app._settings_open
    assert app.layout.current_buffer is app.buffer
    assert app.model == "qwen-plus"
    assert saved.active == "qwen"
    assert saved.profiles["qwen"].api_key == "sk-new-secret"
    assert saved.runtime.temperature == 0.4
    assert app.session.settings.llm_temperature == 0.4
    assert "sk-new-secret" not in app.view.ansi_text
    assert "已保存并切换" in app.view.ansi_text


def test_fullscreen_setting_keeps_existing_key_when_blank(tmp_path, monkeypatch):
    from opennovel.config import Settings
    from opennovel.settings_store import ProfileConfig, UserSettings, load_user_settings, save_user_settings
    from opennovel.ui.app import FullScreenChatApp

    path = tmp_path / "settings.json"
    profile = ProfileConfig(
        name="deepseek", api_key="sk-existing", model="deepseek-chat"
    )
    save_user_settings(
        UserSettings(active="deepseek", profiles={"deepseek": profile}), path
    )
    monkeypatch.setattr(
        "opennovel.llm.build_provider_from_profile",
        lambda profile, settings: FakeProvider(model=profile.model),
    )
    app = FullScreenChatApp(
        FakeProvider(), Settings(output_dir=tmp_path), output=DummyOutput(), settings_path=path
    )
    app._open_settings_screen()
    app.setting_model_buffer.text = "deepseek-reasoner"
    app._save_settings_form()

    saved = load_user_settings(path)
    assert saved.profiles["deepseek"].api_key == "sk-existing"
    assert saved.profiles["deepseek"].model == "deepseek-reasoner"


def test_fullscreen_setting_validation_stays_on_screen(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(
        FakeProvider(),
        Settings(output_dir=tmp_path),
        output=DummyOutput(),
        settings_path=tmp_path / "settings.json",
    )
    app._open_settings_screen()
    app.setting_model_buffer.text = "test-model"
    app._save_settings_form()

    assert app._settings_open
    assert app._settings_error == "配置名不能为空"
    assert app.layout.current_buffer is app.setting_name_buffer


def test_fullscreen_setting_cancel_clears_secret(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(
        FakeProvider(),
        Settings(output_dir=tmp_path),
        output=DummyOutput(),
        settings_path=tmp_path / "settings.json",
    )
    app._open_settings_screen()
    app.setting_api_key_buffer.text = "sk-should-not-linger"
    app._close_settings_screen()

    assert not app._settings_open
    assert app.setting_api_key_buffer.text == ""
    assert app.layout.current_buffer is app.buffer


def test_fullscreen_busy_ignores_input(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(FakeProvider(), Settings(output_dir=tmp_path), output=DummyOutput())
    app._busy = True
    buffer = Buffer()
    buffer.text = "任何输入"
    app._on_accept(buffer)
    assert buffer.text == "任何输入"  # untouched while busy


def test_fullscreen_ask_flow(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(FakeProvider(), Settings(output_dir=tmp_path), output=DummyOutput())
    holder = {"event": __import__("threading").Event(), "value": ""}
    app._pending_ask = holder
    app._busy = True

    buffer = Buffer()
    buffer.text = "雾中城"
    app._on_accept(buffer)
    assert holder["value"] == "雾中城"
    assert buffer.text == ""


def test_fullscreen_ask_accepts_empty_answer(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(FakeProvider(), Settings(output_dir=tmp_path), output=DummyOutput())
    holder = {
        "event": __import__("threading").Event(),
        "value": "not-set",
        "secret": False,
    }
    app._pending_ask = holder
    app._busy = True

    buffer = Buffer()
    buffer.text = ""
    app._on_accept(buffer)
    assert holder["event"].is_set()
    assert holder["value"] == ""
    assert app._pending_ask is None


def test_fullscreen_secret_answer_is_masked(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(FakeProvider(), Settings(output_dir=tmp_path), output=DummyOutput())
    holder = {
        "event": __import__("threading").Event(),
        "value": "",
        "secret": True,
    }
    app._pending_ask = holder
    app._busy = True

    buffer = Buffer()
    buffer.text = "sk-secret-value"
    app._on_accept(buffer)
    assert holder["value"] == "sk-secret-value"
    assert "sk-secret-value" not in app.view.ansi_text
    assert "••••••••" in app.view.ansi_text


def test_fullscreen_busy_allows_only_pending_answer(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(FakeProvider(), Settings(output_dir=tmp_path), output=DummyOutput())
    app._busy = True
    assert app.buffer.read_only()

    app._pending_ask = {"event": __import__("threading").Event(), "value": ""}
    assert not app.buffer.read_only()
    assert app._state_label()[1] == "等待回答"


def test_fullscreen_history_cursor_tracks_latest_output(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(FakeProvider(), Settings(output_dir=tmp_path), output=DummyOutput())
    app.view.add_system(Text("第一行\n第二行\n第三行"))
    assert app._history_cursor_position().y == app.view.ansi_text.count("\n")


def test_fullscreen_header_shows_model(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(
        FakeProvider(model="deepseek-v4-flash"),
        Settings(output_dir=tmp_path),
        output=DummyOutput(),
    )
    assert "deepseek-v4-flash" in app._header_text("deepseek-v4-flash")
    assert "OpenNovel" in app._header_text("m")
    header = app._header_fragments()
    assert "deepseek-v4-flash" in "".join(fragment[1] for fragment in header)
    # body layout: header / history / completions / composer rule / input / footer
    names = [type(c).__name__ for c in app.body.children]
    assert names == [
        "Window",
        "Window",
        "FirstSelectedCompletionsMenu",
        "Window",
        "Window",
        "Window",
    ]
    assert app.body.children[2] is app.completions_menu


def test_completion_menu_selects_first_without_filling_input(tmp_path):
    from prompt_toolkit.application.current import set_app
    from prompt_toolkit.buffer import CompletionState
    from prompt_toolkit.completion import CompleteEvent
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(FakeProvider(), Settings(output_dir=tmp_path), output=DummyOutput())
    app.buffer.text = "/"
    app.buffer.cursor_position = len(app.buffer.text)
    completions = list(
        app.buffer.completer.get_completions(
            app.buffer.document, CompleteEvent(text_inserted=True)
        )
    )
    app.buffer.complete_state = CompletionState(
        original_document=app.buffer.document,
        completions=completions,
    )

    with set_app(app.app):
        control = app.completions_menu.content.content
        content = control.create_content(width=80, height=8)
        first_line_styles = [fragment[0] for fragment in content.get_line(0)]

    assert app.buffer.complete_state.complete_index is None
    assert app.buffer.text == "/"
    assert any("current" in style for style in first_line_styles)


def test_enter_applies_default_first_completion_and_executes(tmp_path, monkeypatch):
    from prompt_toolkit.buffer import CompletionState
    from prompt_toolkit.completion import CompleteEvent
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp
    from opennovel.ui.input import apply_selected_completion

    app = FullScreenChatApp(
        FakeProvider(),
        Settings(output_dir=tmp_path),
        output=DummyOutput(),
        settings_path=tmp_path / "settings.json",
    )
    app.buffer.text = "/sett"
    app.buffer.cursor_position = len(app.buffer.text)
    completions = list(
        app.buffer.completer.get_completions(
            app.buffer.document, CompleteEvent(text_inserted=True)
        )
    )
    app.buffer.complete_state = CompletionState(
        original_document=app.buffer.document,
        completions=completions,
    )
    # The real Application has a running event loop for complete-while-typing;
    # this direct unit test applies a prepared state synchronously.
    app.buffer.completer = None

    assert apply_selected_completion(app.buffer)
    assert app.buffer.text == "/setting"
    app.buffer.validate_and_handle()

    assert app._settings_open
    assert app.view.messages[-1] == ("user", "/setting")


def test_fullscreen_exit_during_ask(tmp_path):
    from opennovel.config import Settings
    from opennovel.ui.app import FullScreenChatApp

    app = FullScreenChatApp(FakeProvider(), Settings(output_dir=tmp_path), output=DummyOutput())
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

    app = FullScreenChatApp(FakeProvider(), Settings(output_dir=tmp_path), output=DummyOutput())
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


def test_free_text_reply_renders_markup_literally(make_session):
    from opennovel.llm import FakeProvider

    provider = FakeProvider(
        replies=[FakeProvider.json_reply({"type": "text", "content": "（您好！）"})]
    )
    session = make_session(provider)
    session.title, session.plot = "雾中城", "剧情"
    handle_command(session, "你好")
    out = session.console.file.getvalue()
    assert "[dim]" not in out
    assert "（您好！）" in out
