from pathlib import Path
from typing import Literal

from .config import OUTPUTS_ROOT, SCENES_DIR
from .story_registry import is_default_story, story_root

AssetKind = Literal[
    "comic",
    "background",
    "scene_character",
    "scene_object",
    "global_character",
    "global_object",
]


def _scene_dir(scene_idx: int, story_id: str | None = None) -> Path:
    return story_root(story_id) / f"{scene_idx:03d}"


def path_for(scene_idx: int, kind: AssetKind, name: str | None = None, story_id: str | None = None) -> Path:
    root = story_root(story_id)
    if kind == "comic":
        return _scene_dir(scene_idx, story_id) / "comic" / "panel.png"
    if kind == "background":
        return _scene_dir(scene_idx, story_id) / "background" / "background.png"
    if kind == "scene_character":
        assert name, "scene_character requires name"
        return _scene_dir(scene_idx, story_id) / "image" / "characters" / f"{name}.png"
    if kind == "scene_object":
        assert name, "scene_object requires name"
        return _scene_dir(scene_idx, story_id) / "image" / "objects" / f"{name}.png"
    if kind == "global_character":
        assert name, "global_character requires name"
        return root / "global" / "characters" / f"{name}.png"
    if kind == "global_object":
        assert name, "global_object requires name"
        return root / "global" / "objects" / f"{name}.png"
    raise ValueError(f"unknown asset kind: {kind}")


def url_for(scene_idx: int, kind: AssetKind, name: str | None = None, story_id: str | None = None) -> str:
    p = path_for(scene_idx, kind, name, story_id=story_id)
    if is_default_story(story_id):
        rel = p.relative_to(SCENES_DIR)
        return f"/assets/scenes/{rel.as_posix()}"
    rel = p.relative_to(OUTPUTS_ROOT)
    return f"/outputs/{rel.as_posix()}"


def resolve_interactive_asset(scene_idx: int, name: str, kind: str, story_id: str | None = None) -> Path:
    """Try scene-local first, fall back to global. Raise with helpful context on miss."""
    scene_kind = "scene_character" if kind == "character" else "scene_object"
    global_kind = "global_character" if kind == "character" else "global_object"
    local = path_for(scene_idx, scene_kind, name, story_id=story_id)
    if local.exists():
        return local
    glob = path_for(scene_idx, global_kind, name, story_id=story_id)
    if glob.exists():
        return glob
    raise FileNotFoundError(
        f"asset not found for story={story_id or 'default'} scene {scene_idx} name={name!r} kind={kind!r}. "
        f"tried: {local} and {glob}"
    )
