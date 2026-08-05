"""Agent loop (v2): intent self-determination + chained tool calls.

The model decides on its own whether to answer conversationally (type=text)
or to act (type=tool_call) — the same way Claude Code switches between chat
and tool-driven work. One user input becomes a short loop: the model either
emits text or requests a tool; tool results are fed back until the model
closes with text or the step budget runs out.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from opennovel.agent.context import build_background, build_history
from opennovel.agent.tools import ToolContext, ToolError, run_tool
from opennovel.llm import ChatMessage, CompletionRequest

MAX_TOOL_STEPS = 10

AGENT_SYSTEM = """你是 OpenNovel 小说写作智能体。你既能和用户正常对话问答，也能调用工具完成写作任务。
行为规则：
1. 对话问答：用户闲聊、讨论剧情、咨询建议时，直接用文本回答，不要调用工具。
2. 写作任务：用户要求写作、续写、修改、查看进度时，调用对应工具。一次请求可以连续调用多个工具（先查看再写、写完再检查）。
3. 信息不足：写书需要书名与剧情，信息不完整时先提问澄清，不要编造。
4. 一致性（不可妥协）：写作必须遵守背景中的风格档案与剧情简报；每写完一章调用 update_plot_state 更新剧情状态；待回收伏笔不要提前揭露。
5. 长文本纪律：章节正文一律通过写作工具（write_chapter / write_scene / rewrite_chapter / edit_chapter）输出，不要在 content 里输出长文；content 只用于简短对话与说明。
6. 工具出错时向用户说明情况，必要时换一种方式重试一次。
7. 只输出 JSON，不要解释。"""


class ToolCall(BaseModel):
    tool: str = Field(description="工具名")
    arguments: dict = Field(default_factory=dict, description="工具参数")


class AgentTurn(BaseModel):
    type: Literal["text", "tool_call"] = Field(default="text", description="本轮输出类型")
    content: str = Field(default="", description="type=text 时的回复文本；也可伴随 tool_call 做简短说明")
    tool_call: ToolCall | None = Field(default=None, description="type=tool_call 时的工具调用")


def run_turn(
    ctx: ToolContext,
    history: list[tuple[str, str]],
    user_text: str,
    *,
    on_agent_text=None,
    on_stage=None,
    max_steps: int = MAX_TOOL_STEPS,
) -> str:
    """Process one user input. Returns the final assistant text.

    - on_agent_text(text): called with each model-authored text piece
      (chat replies / explanations), in order
    - on_stage(text): called with visible tool activity summaries
    """
    messages: list[ChatMessage] = [
        ChatMessage(role="system", content=AGENT_SYSTEM + build_background(ctx)),
        *build_history(history),
        ChatMessage(role="user", content=user_text),
    ]
    last_text = ""
    for step in range(max_steps):
        turn = ctx.provider.complete_structured(
            CompletionRequest(messages=messages), AgentTurn
        )
        if turn.content:
            last_text = turn.content
            if on_agent_text:
                on_agent_text(turn.content)
        if turn.tool_call is None:
            return last_text
        call = turn.tool_call
        if not call.tool:
            return last_text or ""
        try:
            result = run_tool(call.tool, call.arguments, ctx)
        except ToolError as exc:
            messages.append(
                ChatMessage(role="user", content=f"工具 {call.tool} 出错：{exc}。请向用户说明，或换一种方式重试。")
            )
            continue
        messages.append(
            ChatMessage(role="user", content=f"工具 {call.tool} 结果：\n{result.summary}")
        )
        if result.visible and on_stage:
            on_stage(result.summary)
    return last_text or "（本轮操作较多，已暂停。你可以继续指示我下一步做什么。）"
