"""Tests for the v2 agent loop: intent self-determination + tool chaining."""

from dataclasses import replace
from pathlib import Path

from opennovel.agent import MAX_TOOL_STEPS, ToolContext, run_turn
from opennovel.config import Settings
from opennovel.llm import FakeProvider
from opennovel.models import Novel


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


def make_ctx(provider: FakeProvider, tmp_path: Path, **kwargs) -> ToolContext:
    return ToolContext(
        provider=provider,
        settings=replace(Settings(), output_dir=tmp_path),
        title="雾中城",
        plot="少年雨夜进城找妹妹。",
        **kwargs,
    )


def test_text_turn_chats_directly(tmp_path):
    provider = FakeProvider(replies=[text_turn("你好呀，想写什么样的故事？")])
    texts: list[str] = []
    result = run_turn(make_ctx(provider, tmp_path), [], "你好", on_agent_text=texts.append)
    assert result == "你好呀，想写什么样的故事？"
    assert texts == ["你好呀，想写什么样的故事？"]
    assert len(provider.calls) == 1


def test_tool_call_chain_feeds_results_back(tmp_path):
    provider = FakeProvider(
        replies=[tool_turn("read_status", {}), text_turn("进度如上。")]
    )
    novel = Novel(title="雾中城", plot="剧情")
    ctx = make_ctx(provider, tmp_path, novel=novel)
    stages: list[str] = []
    result = run_turn(ctx, [], "现在写到哪了", on_stage=stages.append)
    assert result == "进度如上。"
    assert any("《雾中城》" in s for s in stages)
    assert len(provider.calls) == 2  # tool result was fed back for the 2nd call


def test_unknown_tool_error_feeds_back_and_recovers(tmp_path):
    provider = FakeProvider(
        replies=[
            tool_turn("no_such_tool", {}),
            text_turn("抱歉，我换一种方式。"),
        ]
    )
    result = run_turn(make_ctx(provider, tmp_path), [], "做点什么")
    assert result == "抱歉，我换一种方式。"


def test_max_steps_cutoff(tmp_path):
    replies = [tool_turn("no_such_tool", {}) for _ in range(MAX_TOOL_STEPS + 3)]
    provider = FakeProvider(replies=replies)
    result = run_turn(make_ctx(provider, tmp_path), [], "反复调用")
    assert "已暂停" in result
    assert len(provider.calls) == MAX_TOOL_STEPS


def test_content_accompanies_tool_call(tmp_path):
    provider = FakeProvider(
        replies=[
            tool_turn("read_style", {}, content="我先看看风格。"),
            text_turn("这就是当前风格。"),
        ]
    )
    novel = Novel(title="雾中城", plot="剧情")
    novel.style_profile.tone = "冷峻"
    texts: list[str] = []
    ctx = make_ctx(provider, tmp_path, novel=novel)
    result = run_turn(ctx, [], "风格是什么", on_agent_text=texts.append)
    assert texts == ["我先看看风格。", "这就是当前风格。"]
    assert result == "这就是当前风格。"


def test_history_window_feeds_previous_turns(tmp_path):
    provider = FakeProvider(replies=[text_turn("好的。")])
    history = [
        ("user", "我想写一本悬疑小说"),
        ("assistant", "好啊，主角叫什么？"),
        ("user", "林晚"),
        ("system", "（UI 噪音，不应进入上下文）"),
    ]
    run_turn(make_ctx(provider, tmp_path), history, "开始写吧")
    user_contents = [m.content for m in provider.calls[0].messages if m.role == "user"]
    assert "林晚" in user_contents
    assert "UI 噪音" not in user_contents
    assert user_contents[-1] == "开始写吧"
