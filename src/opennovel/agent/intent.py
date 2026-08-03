"""LLM intent routing for chat input (MVP step 7).

A light single call classifies free-text user input into a command intent so
natural language like "把第二章重写得更紧张" maps to /rewrite 2.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from opennovel.llm import ChatMessage, CompletionRequest, Provider

INTENT_SYSTEM = """你是 OpenNovel 小说写作助手的意图分类器。把用户的自然语言输入归类为一种意图：
- start_new：用户想开始一本新书（提到书名/新故事/新剧情）
- append_plot：补充、扩展当前剧情（加情节、加设定、加人物）
- write_now：开始写作当前书（继续写/开写/写书/写作）
- rewrite_chapter：要求重写、修改某个章节（需提取 chapter_no，1 起）
- status：询问进度、状态、章节情况
- checks：询问检查报告、风格检查、剧情一致性
- help：询问用法、能做什么
- other：以上都不匹配（此时仍可给 suggestion）
chapter_no 仅在 rewrite_chapter 时填，其他意图留 0。suggestion 使用纯文本，不要包含任何 markdown 或方括号标记。
只输出 JSON，不要解释。"""


class IntentKind(StrEnum):
    START_NEW = "start_new"
    APPEND_PLOT = "append_plot"
    WRITE_NOW = "write_now"
    REWRITE_CHAPTER = "rewrite_chapter"
    STATUS = "status"
    CHECKS = "checks"
    HELP = "help"
    OTHER = "other"


class Intent(BaseModel):
    """Classification result for one free-text input."""

    kind: IntentKind
    chapter_no: int = Field(default=0, ge=0, description="rewrite_chapter 时的章节号（1 起）")
    suggestion: str = Field(default="", description="other 意图时给用户的提示")


def classify_intent(provider: Provider, text: str) -> Intent:
    """Classify user input into an Intent (one light LLM call).

    Falls back to APPEND_PLOT on any failure, so chat input never breaks the
    session.
    """
    request = CompletionRequest(
        messages=[
            ChatMessage(role="system", content=INTENT_SYSTEM),
            ChatMessage(role="user", content=text),
        ],
        max_tokens=128,
        temperature=0.0,
    )
    try:
        return provider.complete_structured(request, Intent)
    except Exception:
        return Intent(kind=IntentKind.APPEND_PLOT, suggestion=text)
