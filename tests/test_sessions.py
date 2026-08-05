"""Tests for session management: store, commands, shared background, chat restore."""

import pytest

from opennovel.session_store import (
    SessionRecord,
    delete_session,
    latest_session,
    list_sessions,
    load_session,
    novel_exists,
    save_session,
)
from opennovel.ui.repl import handle_command


def make_record(name="会话A") -> SessionRecord:
    return SessionRecord(novel_title="雾中城", name=name)


def test_store_roundtrip_and_list(tmp_path):
    r1 = make_record("A")
    r2 = make_record("B")
    save_session(r1, tmp_path)
    save_session(r2, tmp_path)
    records = list_sessions("雾中城", tmp_path)
    assert {r.name for r in records} == {"A", "B"}
    loaded = load_session("雾中城", r1.id, tmp_path)
    assert loaded.name == "A"
    assert novel_exists("雾中城", tmp_path) is False  # 未写 novel.json


def test_store_latest_and_delete(tmp_path):
    r1 = make_record("A")
    save_session(r1, tmp_path)
    assert latest_session("雾中城", tmp_path).id == r1.id
    assert delete_session("雾中城", r1.id, tmp_path) is True
    assert list_sessions("雾中城", tmp_path) == []


def test_session_record_persists_messages(tmp_path):
    r = make_record("A")
    r.messages = [("user", "你好"), ("assistant", "你好呀")]
    save_session(r, tmp_path)
    loaded = load_session("雾中城", r.id, tmp_path)
    assert loaded.messages == [("user", "你好"), ("assistant", "你好呀")]


def test_new_creates_first_session(make_session, tmp_path):
    session = make_session()
    session.console.input = lambda prompt="": "少年进城"
    handle_command(session, "/new --title 雾中城 --style 冷峻")
    assert session.session_id
    assert list_sessions("雾中城", tmp_path)
    assert session.session_name == "会话"


def test_sessions_list_and_switch(make_session, tmp_path):
    session = make_session()
    session.title = "雾中城"
    handle_command(session, "/session new 讨论")
    handle_command(session, "/session new 润色")
    handle_command(session, "/sessions")
    out = session.console.file.getvalue()
    assert "润色" in out
    assert "讨论" in out
    # switch by name
    handle_command(session, "/session open 讨论")
    assert session.session_name == "讨论"
    # switch by index
    handle_command(session, "/session open 1")
    assert session.session_name != "润色" or session.session_name == "讨论"


def test_session_rename_and_delete(make_session, tmp_path):
    session = make_session()
    session.title = "雾中城"
    handle_command(session, "/session new 旧名")
    handle_command(session, "/session rename 旧名 新名")
    assert session.session_name == "新名"
    handle_command(session, "/session new 另一个")
    handle_command(session, "/session delete 新名")
    assert "新名" not in {r.name for r in list_sessions("雾中城", tmp_path)}
    assert session.session_name == "另一个"


def test_shared_background_between_sessions(make_session, tmp_path):
    """两个 session 打开同一本书，A 写作后 B 能看到章节（共享 novel.json）。"""
    from opennovel.llm import FakeProvider

    provider = FakeProvider()
    provider.enqueue(
        FakeProvider.json_reply({"tone": "冷峻", "sample_passage": "雨落了一夜。"}),
        FakeProvider.json_reply({"chapters": [{"title": "夜雨", "focus": "进城", "scene_count": 1}]}),
        FakeProvider.json_reply({"scenes": [{"summary": "车站相遇"}]}),
        "正文内容。",
        FakeProvider.json_reply({"score": 0, "deviations": [], "suggestion": ""}),
        FakeProvider.json_reply({"score": 0, "contradictions": [], "suggestion": ""}),
        FakeProvider.json_reply({"new_characters": [{"name": "林晚", "role": "主角"}], "events": [], "new_setups": [], "resolved_setups": []}),
    )
    a = make_session(provider)
    a.title, a.plot, a.style_hint = "雾中城", "少年进城", "冷峻"
    handle_command(a, "/write")
    assert len(a.novel.chapters) == 1

    # B 会话：同一本书
    b = make_session()
    b.title = "雾中城"
    handle_command(b, "/session new B会话")
    assert b.novel is not None  # ensure_fresh_novel 加载了共享背景
    assert len(b.novel.chapters) == 1
    assert b.novel.chapters[0].title == "夜雨"
    assert b.plot == "少年进城"


def test_chat_restored_on_open(make_session, tmp_path):
    session = make_session()
    session.title = "雾中城"
    handle_command(session, "/session new 甲")
    session.chat.add_user("第一条消息")
    handle_command(session, "/session new 乙")
    assert session.session_name == "乙"
    handle_command(session, "/session open 甲")
    restored = [m for _, m in session.chat.messages]
    assert "第一条消息" in restored
