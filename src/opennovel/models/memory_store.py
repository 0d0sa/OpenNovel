"""JSON persistence for per-novel memory (novels/<title>/memory.json).

Atomic write, same pattern as session records. Missing file means the book
predates memory v2 — migrate on first access (see ToolContext.fresh_memory).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from opennovel.models.memory import NovelMemory


def default_memory_path(title: str, base_dir: Path = Path("novels")) -> Path:
    return base_dir / title / "memory.json"


def load_memory(title: str, base_dir: Path = Path("novels")) -> NovelMemory | None:
    path = default_memory_path(title, base_dir)
    if not path.exists():
        return None
    return NovelMemory.model_validate_json(path.read_text(encoding="utf-8"))


def save_memory(memory: NovelMemory, path: Path) -> Path:
    """Write a memory record atomically. Returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".memory-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(memory.model_dump_json(indent=2))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path
