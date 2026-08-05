"""Session records: one novel can have multiple sessions.

Each session persists its own chat history to `novels/<title>/sessions/<id>.json`.
All sessions of one book share the same Novel (background knowledge) stored in
`novels/<title>/novel.json` — sessions only differ in conversation state.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from opennovel.models.storage import default_novel_path


class SessionRecord(BaseModel):
    """One persisted session: identity, timestamps, and chat history."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = "会话"
    novel_title: str = ""
    created_at: str = Field(default_factory=lambda: _now())
    updated_at: str = Field(default_factory=lambda: _now())
    messages: list[tuple[str, str]] = Field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sessions_dir(novel_title: str, base_dir: Path = Path("novels")) -> Path:
    return base_dir / novel_title / "sessions"


def session_path(novel_title: str, session_id: str, base_dir: Path = Path("novels")) -> Path:
    return sessions_dir(novel_title, base_dir) / f"{session_id}.json"


def list_sessions(novel_title: str, base_dir: Path = Path("novels")) -> list[SessionRecord]:
    """All sessions for a book, most recently updated first."""
    directory = sessions_dir(novel_title, base_dir)
    records = []
    if directory.exists():
        for file in directory.glob("*.json"):
            try:
                records.append(SessionRecord.model_validate_json(file.read_text(encoding="utf-8")))
            except Exception:
                continue
    records.sort(key=lambda r: r.updated_at, reverse=True)
    return records


def load_session(novel_title: str, session_id: str, base_dir: Path = Path("novels")) -> SessionRecord | None:
    path = session_path(novel_title, session_id, base_dir)
    if not path.exists():
        return None
    return SessionRecord.model_validate_json(path.read_text(encoding="utf-8"))


def save_session(record: SessionRecord, base_dir: Path = Path("novels")) -> Path:
    """Write a session record atomically."""
    record.updated_at = _now()
    path = session_path(record.novel_title, record.id, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".session-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(record.model_dump_json(indent=2))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def delete_session(novel_title: str, session_id: str, base_dir: Path = Path("novels")) -> bool:
    path = session_path(novel_title, session_id, base_dir)
    if path.exists():
        path.unlink()
        return True
    return False


def latest_session(novel_title: str, base_dir: Path = Path("novels")) -> SessionRecord | None:
    records = list_sessions(novel_title, base_dir)
    return records[0] if records else None


def novel_exists(novel_title: str, base_dir: Path = Path("novels")) -> bool:
    return default_novel_path(novel_title, base_dir).exists()
