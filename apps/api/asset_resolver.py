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


def thumb_url(original_url: str, width: int = 400) -> str:
    """Generate a proxied thumbnail URL for an internal image path."""
    return f"/api/image/proxy?path={original_url}&width={width}"


def resolve_asset_url_to_path(url: str, *, materialize_dir: Path | None = None) -> Path | None:
    """Resolve an asset URL/served-path into a local file Path on disk.

    Handles every form an asset URL can take in this project:
      - ``/outputs/...``        -> ``OUTPUTS_ROOT/...`` (local storage)
      - ``/assets/scenes/...``  -> ``SCENES_DIR/...`` (default-story preset assets)
      - ``http(s)://...``       -> downloaded into ``materialize_dir`` (object storage)
      - ``data:...``            -> decoded into ``materialize_dir``
      - bare filesystem path that already exists

    Returns ``None`` (never raises) when the asset cannot be resolved to an
    existing file, so callers can simply skip un-resolvable references.

    NOTE: this is the single source of truth for URL->Path resolution. The old
    ``narrative_generator`` ad-hoc ``PROJECT_ROOT / url.lstrip('/')`` logic was
    wrong (``OUTPUTS_ROOT`` is ``PROJECT_ROOT/outputs/webdemo``, so it dropped the
    ``webdemo`` segment and silently lost every custom-prop reference image).
    """
    u = (url or "").strip()
    if not u:
        return None
    if u.startswith("/outputs/"):
        p = (OUTPUTS_ROOT / u[len("/outputs/"):]).resolve()
        return p if p.is_file() else None
    if u.startswith("/assets/scenes/"):
        p = (SCENES_DIR / u[len("/assets/scenes/"):]).resolve()
        return p if p.is_file() else None
    if u.startswith(("http://", "https://", "data:")):
        try:
            data = _fetch_asset_bytes(u)
        except Exception:
            return None
        import tempfile

        target_dir = materialize_dir or Path(tempfile.gettempdir())
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            out = target_dir / _asset_filename(u)
            out.write_bytes(data)
            return out
        except Exception:
            return None
    p = Path(u)
    return p.resolve() if p.is_file() else None


def _fetch_asset_bytes(url: str) -> bytes:
    if url.startswith("data:"):
        import base64

        _, _, raw = url.partition(",")
        return base64.b64decode(raw)
    import requests

    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.content


def _asset_filename(url: str) -> str:
    """A stable, filesystem-safe filename for a remote/inline asset URL."""
    import hashlib

    if url.startswith("data:"):
        digest = hashlib.md5(url[:256].encode("utf-8")).hexdigest()[:16]
        return f"ref_{digest}.png"
    from urllib.parse import urlparse

    name = Path(urlparse(url).path).name or ""
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
    suffix = Path(name).suffix or ".png"
    return f"ref_{digest}{suffix}"


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
