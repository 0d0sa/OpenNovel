"""Tests for streaming and the interactive chat session."""

from dataclasses import replace

from opennovel.agent import write_novel
from opennovel.config import Settings
from opennovel.llm import CompletionRequest, FakeProvider
from opennovel.models import Scene, SceneStatus
from opennovel.ui.repl import handle_command


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


def test_unknown_command_prints_error(make_session):
    session = make_session()
    assert handle_command(session, "/nope")
    assert "未知命令" in session.console.file.getvalue()


def test_exit_command(make_session):
    session = make_session()
    assert handle_command(session, "/exit") is False


def test_free_text_requires_new_book_first(make_session):
    provider = FakeProvider(
        replies=[
            FakeProvider.json_reply(
                {"type": "text", "content": "还没有书，请先 /new 创建，或直接告诉我书名和剧情。"}
            )
        ]
    )
    session = make_session(provider)
    handle_command(session, "加一段剧情")
    assert "先 /new" in session.console.file.getvalue()


def test_exit_during_new_prompts_aborts(make_session):
    session = make_session()
    lines = iter(["雾中城", "/exit"])
    session.console.input = lambda prompt="": next(lines)
    handle_command(session, "/new")
    assert session.exiting is True
    assert session.plot == ""  # 未完成创建


def test_exit_not_consumed_as_title(make_session):
    """/exit typed at the 书名 prompt must exit, not become the title."""
    session = make_session()
    session.console.input = lambda prompt="": "/exit"
    handle_command(session, "/new")
    assert session.exiting is True
    assert session.title == ""


def test_other_command_during_new_reprompts(make_session):
    session = make_session()
    lines = iter(["/status", "雾中城", "剧情", ""])
    session.console.input = lambda prompt="": next(lines)
    handle_command(session, "/new")
    assert session.title == "雾中城"
    assert session.plot == "剧情"
    assert "命令已执行" in session.console.file.getvalue()


def test_new_sets_up_plot_and_append(make_session):
    session = make_session()
    answers = iter(["雾中城", "少年进城找妹妹", "冷峻"])
    session.ask = lambda prompt: next(answers)
    handle_command(session, "/new")
    assert session.title == "雾中城"
    assert session.plot == "少年进城找妹妹"
    assert session.style_hint == "冷峻"
    # v2: free text goes through the agent loop; the model decides to append
    provider = FakeProvider(
        replies=[
            FakeProvider.json_reply(
                {
                    "type": "tool_call",
                    "content": "我把这段补进剧情。",
                    "tool_call": {"tool": "append_plot", "arguments": {"text": "他遇到了老警察。"}},
                }
            ),
            FakeProvider.json_reply({"type": "text", "content": "已补充。"}),
        ]
    )
    session.provider = provider
    handle_command(session, "他遇到了老警察。")
    assert "老警察" in session.plot
    assert "已追加到剧情" in session.console.file.getvalue()


def test_new_with_plot_file(make_session, tmp_path):
    plot_file = tmp_path / "plot.txt"
    plot_file.write_text("从文件来的剧情", encoding="utf-8")
    session = make_session()
    session.ask = lambda prompt: "雾中城" if "书名" in prompt else ""
    handle_command(session, f"/new --plot-file {plot_file}")
    assert session.plot == "从文件来的剧情"


def test_status_and_style_with_no_novel(make_session):
    session = make_session()
    handle_command(session, "/status")
    assert "尚未开始" in session.console.file.getvalue()
    handle_command(session, "/style")
    assert "尚未开始" in session.console.file.getvalue()


def test_write_command_runs_pipeline(make_session, tmp_path):
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
    session = make_session(provider)
    session.title, session.plot = "雾中城", "少年进城"
    handle_command(session, "/write")
    novel = session.novel
    assert novel is not None
    assert len(novel.chapters) == 1
    assert novel.chapters[0].scenes[0].content == "正文流式内容。"
    assert novel.chapters[0].style_report is not None
    assert novel.chapters[0].plot_report is not None
    assert (tmp_path / "雾中城" / "novel.json").exists()


def test_write_without_new_prompts(make_session):
    session = make_session()
    handle_command(session, "/write")
    assert "先 /new" in session.console.file.getvalue()


def test_checks_show_reports(make_session):
    from opennovel.memory import PlotConsistency, StyleDeviation
    from opennovel.models import Chapter, Novel

    session = make_session()
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


def test_rewrite_updates_chapter(make_session, tmp_path):
    from opennovel.models import Chapter, Novel

    provider = FakeProvider(replies=["重写后的正文"])
    session = make_session(provider)
    session.novel = Novel(
        title="雾中城",
        chapters=[Chapter(title="夜雨", scenes=[Scene(summary="s", content="旧正文", status=SceneStatus.WRITTEN)])],
    )
    handle_command(session, "/rewrite 1")
    assert session.novel.chapters[0].scenes[0].content == "重写后的正文"
    assert session.novel.chapters[0].style_report is None
    assert (tmp_path / "雾中城" / "novel.json").exists()


def test_rewrite_out_of_range(make_session):
    from opennovel.models import Novel

    session = make_session()
    session.novel = Novel(title="雾中城")
    handle_command(session, "/rewrite 5")
    assert "超出范围" in session.console.file.getvalue()


def test_write_novel_stream_callback(tmp_path):
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
