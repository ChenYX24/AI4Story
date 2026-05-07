"""On-the-fly image resize + WebP conversion with filesystem cache.

GET /api/image/proxy?path=/outputs/.../comic.png&width=400

- Reads original from the filesystem (scenes/ or outputs/).
- Resizes to the requested width (maintaining aspect ratio).
- Converts to WebP (quality 80).
- Caches the result on disk so subsequent requests are instant.
- Sets immutable cache headers (1 year) since width is in the filename.
"""

import hashlib
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..config import OUTPUTS_ROOT, PROJECT_ROOT, SCENES_DIR

log = logging.getLogger(__name__)

router = APIRouter(tags=["image"])

# Thumbnails are cached in outputs/.thumbs/ so they survive deploys.
_THUMB_ROOT = OUTPUTS_ROOT / ".thumbs"

# Allowed source directories (whitelist to prevent path traversal).
_ALLOWED_ROOTS = {
    "/assets/scenes/": SCENES_DIR,
    "/outputs/": OUTPUTS_ROOT,
}


def _resolve_src_path(url_path: str) -> Path | None:
    """Map a URL path like /assets/scenes/001/comic/panel.png to a filesystem path."""
    for prefix, root in _ALLOWED_ROOTS.items():
        if url_path.startswith(prefix):
            rel = url_path[len(prefix):].lstrip("/")
            # prevent path traversal
            if ".." in rel:
                return None
            return root / rel
    return None


@router.get("/image/proxy")
def image_proxy(
    path: str = Query(..., description="URL path of the original image, e.g. /assets/scenes/001/comic/panel.png"),
    width: int = Query(400, ge=50, le=1920, description="Target width in pixels"),
):
    src = _resolve_src_path(path)
    if src is None or not src.exists():
        raise HTTPException(status_code=404, detail=f"source image not found: {path}")

    # Cache key: hash of (path, width) -> stable filename
    cache_key = hashlib.sha256(f"{path}:{width}".encode()).hexdigest()[:16]
    cache_dir = _THUMB_ROOT / cache_key[:2]
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{cache_key}.webp"

    if not cache_file.exists():
        try:
            from PIL import Image

            im = Image.open(src)
            if im.mode in ("RGBA", "P", "LA"):
                im = im.convert("RGBA")
            else:
                im = im.convert("RGB")

            # resize maintaining aspect ratio
            w_percent = width / im.width
            h = int(im.height * w_percent)
            im = im.resize((width, h), Image.LANCZOS)

            im.save(cache_file, format="WEBP", quality=80)
            log.info("[image-proxy] generated %s (%dx%d) from %s", cache_file.name, width, h, path)
        except Exception as e:
            log.warning("[image-proxy] failed to generate thumbnail for %s: %s", path, e)
            # fall back to serving original
            return FileResponse(src, media_type="image/png")

    return FileResponse(
        cache_file,
        media_type="image/webp",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )
