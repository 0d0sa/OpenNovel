"""JSON persistence for novels.

One book = one JSON file (default `novels/<title>/novel.json`). MVP keeps
everything in a single file; split files come later if size demands it.
"""

from __future__ import annotations

import json
from pathlib import Path

from opennovel.models.novel import Novel


def save_novel(novel: Novel, path: Path) -> Path:
    """Persist a novel as JSON. Creates parent directories. Returns the path."""
    path = Path(path)
    if path.suffix != ".json":
        path = path.with_suffix(".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(novel.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_novel(path: Path) -> Novel:
    """Load a novel from JSON. Raises ValidationError on invalid content."""
    return Novel.model_validate_json(Path(path).read_text(encoding="utf-8"))


def default_novel_path(title: str, base_dir: Path = Path("novels")) -> Path:
    """Default per-book file path, e.g. novels/<title>/novel.json."""
    return base_dir / title / "novel.json"


def save_novel_json(novel: Novel) -> dict:
    """Serialize a novel to a plain JSON dict (for tests/tooling)."""
    return json.loads(novel.model_dump_json())
