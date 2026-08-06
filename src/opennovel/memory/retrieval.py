"""Full-text retrieval over novel content (L2 memory, zero dependencies).

Sentence-level substring matching + role-name dictionary. The agent decides
whether to call `search_memory` (tool) to locate content, then reads the
chapter in full via `read_chapter`.
"""

from __future__ import annotations

import re

_SENT_RE = re.compile(r"[^。！？…；\n]+[。！？…]?")
_WORD_SPLIT = re.compile(r"[\s，。、；：！？…（）【】「」『』]+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.findall(text) if s.strip()]


def search_memory(novel, memory, query: str, limit: int = 5) -> list[str]:
    """Return up to `limit` matching snippets, each prefixed with its source.

    `novel` and `memory` are duck-typed (Novel / NovelMemory) so this module
    stays importable while `models` is still being initialized.
    """
    if not query.strip():
        return []
    tokens = [t for t in _WORD_SPLIT.split(query) if t]
    state = memory.plot_state if memory is not None else novel.plot_state
    names = [n for n in (state.characters if state else {}) if n]

    hits: list[tuple[float, str, int]] = []

    def score_text(text: str, source: str, order: int) -> None:
        if query in text or any(t in text for t in tokens):
            score = 2.0 if query in text else 1.0
            score += sum(1.0 for n in names if n and n in text)
            hits.append((score, source + text, order))

    order = 0
    for i, chapter in enumerate(novel.chapters, 1):
        full = "\n\n".join(s.content for s in chapter.scenes if s.content)
        for sent in split_sentences(full):
            order += 1
            score_text(sent, f"[第{i}章] ", order)
    if memory is not None:
        for s in memory.chapter_summaries:
            for line in (s.overview, s.hook, *s.events, *s.key_facts):
                order += 1
                score_text(line, f"[第{s.chapter_no}章·摘要] ", order)
    hits.sort(key=lambda h: (h[0], -h[2]), reverse=True)
    return [h[1] for h in hits[:limit]]
