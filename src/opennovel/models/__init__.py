"""Core data models: Novel, Chapter, Scene, Character."""

from opennovel.models.novel import (
    Chapter,
    ChapterPlan,
    Character,
    Novel,
    Scene,
    SceneStatus,
)
from opennovel.models.storage import (
    default_novel_path,
    load_novel,
    save_novel,
    save_novel_json,
)

__all__ = [
    "Chapter",
    "ChapterPlan",
    "Character",
    "Novel",
    "Scene",
    "SceneStatus",
    "default_novel_path",
    "load_novel",
    "save_novel",
    "save_novel_json",
]
