from pathlib import Path
from typing import Literal

from .config import SCENES_DIR

AssetKind = Literal[
    "comic",
    "background",
    "scene_character",
    "scene_object",
    "global_character",
    "global_object",
]


def _scene_dir(scene_idx: int) -> Path:
    return SCENES_DIR / f"{scene_idx:03d}"


def path_for(scene_idx: int, kind: AssetKind, name: str | None = None) -> Path:
    if kind == "comic":
        return _scene_dir(scene_idx) / "comic" / "panel.png"
    if kind == "background":
        return _scene_dir(scene_idx) / "background" / "background.png"
    if kind == "scene_character":
        assert name, "scene_character requires name"
        return _scene_dir(scene_idx) / "image" / "characters" / f"{name}.png"
    if kind == "scene_object":
        assert name, "scene_object requires name"
        return _scene_dir(scene_idx) / "image" / "objects" / f"{name}.png"
    if kind == "global_character":
        assert name, "global_character requires name"
        return SCENES_DIR / "global" / "characters" / f"{name}.png"
    if kind == "global_object":
        assert name, "global_object requires name"
        return SCENES_DIR / "global" / "objects" / f"{name}.png"
    raise ValueError(f"unknown asset kind: {kind}")


def url_for(scene_idx: int, kind: AssetKind, name: str | None = None) -> str:
    p = path_for(scene_idx, kind, name)
    rel = p.relative_to(SCENES_DIR)
    return f"/assets/scenes/{rel.as_posix()}"


def resolve_interactive_asset(scene_idx: int, name: str, kind: str) -> Path:
    """Try scene-local first, fall back to global. Raise with helpful context on miss."""
    scene_kind = "scene_character" if kind == "character" else "scene_object"
    global_kind = "global_character" if kind == "character" else "global_object"
    local = path_for(scene_idx, scene_kind, name)
    if local.exists():
        return local
    glob = path_for(scene_idx, global_kind, name)
    if glob.exists():
        return glob
    raise FileNotFoundError(
        f"asset not found for scene {scene_idx} name={name!r} kind={kind!r}. "
        f"tried: {local} and {glob}"
    )
