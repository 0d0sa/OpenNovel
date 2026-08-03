"""Tests for streaming and the interactive REPL."""

from dataclasses import replace
from io import StringIO

from rich.console import Console

from opennovel.agent import write_novel
from opennovel.config import Settings
from opennovel.llm import ChatMessage, CompletionRequest, FakeProvider
from opennovel.memory import PlotState
from opennovel.models import Scene, SceneStatus
from opennovel.ui.repl import Session, handle_command


def test_stream_complete_yields_whole_text():
    provider = FakeProvider(replies=["正文内容"])
    chunks = list(provider.stream_complete(CompletionRequest(messages=[])))
    assert chunks == ["正文内容"]


def test_stream_complete_collects_deltas_in_write_scene():
    from opennovel.agent.planning import write_scene

    provider = FakeProvider(replies=["一二三"])
    tokens: list[str] = []
    text = write_scene(
        provider,
        Scene(summary="场景"),
        "锚点",
        "简报",
        "",
        100,
        stream_callback=lambda t: tokens.append(t),
    )
    assert text == "一二三"
    assert tokens == ["一二三"]


def make_session(provider: FakeProvider, tmp_path, **overrides) -> Session:
    settings = replace(Settings(), output_dir=tmp_path, max_chapters=1, chapter_target_chars=200)
    if overrides:
        settings = replace(settings, **overrides)
    console = Console(file=StringIO(), force_terminal=False, width=100)
    return Session(provider=provider, settings=settings, console=console)


def test_unknown_command_prints_error():
    session = make_session(FakeProvider(), "/tmp/x")
    assert handle_command(session, "/nope")
    assert "未知命令" in session.console.file.getvalue()


def test_exit_command():
    session = make_session(FakeProvider(), "/tmp/x")
    assert handle_command(session, "/exit") is False


def test_free_text_requires_new_book_first():
    session = make_session(FakeProvider(), "/tmp/x")
    handle_command(session, "加一段剧情")
    assert "先 /new" in session.console.file.getvalue()


def test_new_sets_up_plot_and_append():
    session = make_session(FakeProvider(), "/tmp/x")
    answers = iter(["雾中城", "少年进城找妹妹", "冷峻"])
    session.ask = lambda prompt: next(answers)
    handle_command(session, "/new")
    assert session.title == "雾中城"
    assert session.plot == "少年进城找妹妹"
    assert session.style_hint == "冷峻"
    handle_command(session, "他遇到了老警察。")
    assert "老警察" in session.plot
    assert "已追加" in session.console.file.getvalue()


def test_new_with_plot_file(tmp_path):
    plot_file = tmp_path / "plot.txt"
    plot_file.write_text("从文件来的剧情", encoding="utf-8")
    session = make_session(FakeProvider(), tmp_path)
    session.ask = lambda prompt: "雾中城" if "书名" in prompt else ""
    handle_command(session, f"/new --plot-file {plot_file}")
    assert session.plot == "从文件来的剧情"


def test_status_and_style_with_no_novel():
    session = make_session(FakeProvider(), "/tmp/x")
    handle_command(session, "/status")
    assert "尚未开始" in session.console.file.getvalue()
    handle_command(session, "/style")
    assert "尚未开始" in session.console.file.getvalue()


def test_write_command_runs_pipeline(tmp_path):
    provider = FakeProvider()
    provider.enqueue(
        FakeProvider.json_reply({"tone": "冷峻", "pov": "第三人称限知", "sample_passage": "雨落了一夜。"}),
        FakeProvider.json_reply({"chapters": [{"title": "夜雨", "focus": "进城", "scene_count": 1}]}),
        FakeProvider.json_reply({"scenes": [{"summary": "车站相遇"}]}),
        "正文流式内容。",
        FakeProvider.json_reply({"score": 0, "deviations": [], "suggestion": ""}),
        FakeProvider.json_reply({"score": 0, "contradictions": [], "suggestion": ""}),
        FakeProvider.json_reply({"new_characters": [{"name": "林晚", "role": "主角"}], "events": [], "new_setups": [], "resolved_setups": []}),
    )
    session = make_session(provider, tmp_path)
    session.title, session.plot = "雾中城", "少年进城"
    handle_command(session, "/write")
    novel = session.novel
    assert novel is not None
    assert len(novel.chapters) == 1
    assert novel.chapters[0].scenes[0].content == "正文流式内容。"
    assert novel.chapters[0].style_report is not None
    assert novel.chapters[0].plot_report is not None
    assert (tmp_path / "雾中城" / "novel.json").exists()


def test_write_without_new_prompts():
    session = make_session(FakeProvider(), "/tmp/x")
    handle_command(session, "/write")
    assert "先 /new" in session.console.file.getvalue()


def test_checks_show_reports(tmp_path):
    provider = FakeProvider()
    session = make_session(provider, tmp_path)
    from opennovel.memory import PlotConsistency, StyleDeviation
    from opennovel.models import Chapter, Novel

    chapter = Chapter(
        title="夜雨",
        scenes=[Scene(summary="s", content="正文", status=SceneStatus.WRITTEN)],
        style_report=StyleDeviation(score=4, deviations=["语气轻佻"], suggestion="改为克制"),
        plot_report=PlotConsistency(score=1, contradictions=[], suggestion=""),
    )
    session.novel = Novel(title="雾中城", chapters=[chapter])
    handle_command(session, "/checks")
    out = session.console.file.getvalue()
    assert "偏离度 4/5" in out
    assert "语气轻佻" in out
    assert "矛盾度 1/5" in out


def test_rewrite_updates_chapter(tmp_path):
    from opennovel.agent.planning import rewrite_chapter

    provider = FakeProvider(replies=["重写后的正文"])
    session = make_session(provider, tmp_path)
    from opennovel.models import Chapter, Novel

    session.novel = Novel(
        title="雾中城",
        chapters=[Chapter(title="夜雨", scenes=[Scene(summary="s", content="旧正文", status=SceneStatus.WRITTEN)])],
    )
    handle_command(session, "/rewrite 1")
    assert session.novel.chapters[0].scenes[0].content == "重写后的正文"
    assert session.novel.chapters[0].style_report is None
    assert (tmp_path / "雾中城" / "novel.json").exists()


def test_rewrite_out_of_range(tmp_path):
    session = make_session(FakeProvider(), tmp_path)
    from opennovel.models import Novel

    session.novel = Novel(title="雾中城")
    handle_command(session, "/rewrite 5")
    assert "超出范围" in session.console.file.getvalue()


def test_write_novel_stream_callback(tmp_path):
    from opennovel.config import Settings

    provider = FakeProvider()
    provider.enqueue(
        FakeProvider.json_reply({"tone": "冷峻", "sample_passage": "雨落了一夜。"}),
        FakeProvider.json_reply({"chapters": [{"title": "夜雨", "focus": "进城", "scene_count": 1}]}),
        FakeProvider.json_reply({"scenes": [{"summary": "车站"}]}),
        "流式正文",
        FakeProvider.json_reply({"score": 0, "deviations": [], "suggestion": ""}),
        FakeProvider.json_reply({"score": 0, "contradictions": [], "suggestion": ""}),
        FakeProvider.json_reply({"new_characters": [], "events": [], "new_setups": [], "resolved_setups": []}),
    )
    stages: list[str] = []
    tokens: list[str] = []
    novel = write_novel(
        provider,
        replace(Settings(), output_dir=tmp_path, max_chapters=1, chapter_target_chars=200),
        "雾中城",
        "剧情",
        on_stage=lambda s: stages.append(s),
        on_token=lambda t: tokens.append(t),
    )
    assert tokens == ["流式正文"]
    assert stages
    assert novel.chapters[0].scenes[0].content == "流式正文"
