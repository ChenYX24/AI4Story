"""
把 scenes/ 里的官方故事（小红帽）录入新表 + 把所有图片上传 OSS。

依赖：oss2，需要 env：
  MINDSHOW_OSS_BUCKET   = mindshow-pku
  MINDSHOW_OSS_ENDPOINT = https://oss-cn-shenzhen.aliyuncs.com
  MINDSHOW_OSS_PREFIX   = mindshow/   (默认)
  MINDSHOW_OSS_AK_ID
  MINDSHOW_OSS_AK_SECRET
  MINDSHOW_STORAGE      = oss

执行幂等 — 重复跑会覆盖（OSS put_object + 表 ON CONFLICT UPDATE）。
完成后所有 cover_url / comic_url / background_url / asset.url 全是 OSS https URL，
读路径不再依赖 scenes/ 文件夹。

用法：
    python -m scripts.seed_official                # 录入默认故事 little_red_riding_hood
    python -m scripts.seed_official --dry-run      # 只扫描不上传不写库
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from apps.api import db  # noqa: E402
from apps.api.storage import get_storage  # noqa: E402

DEFAULT_STORY_ID = "little_red_riding_hood"
DEFAULT_TITLE = "小红帽 · 森林冒险"
SCENES_DIR = REPO_ROOT / "scenes"


def _read_json(p: Path) -> dict:
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _content_type_for(p: Path) -> str:
    ct, _ = mimetypes.guess_type(p.name)
    return ct or "application/octet-stream"


def _scene_dirs() -> Iterator[Path]:
    for child in sorted(SCENES_DIR.iterdir()):
        if not child.is_dir():
            continue
        if child.name == "global":
            continue
        if not (child.name.isdigit() and len(child.name) == 3):
            continue
        yield child


def _zh_to_type(zh: str) -> str:
    return "narrative" if zh == "叙事场景" else "interactive"


def _scene_type(scene_obj: dict) -> str:
    return _zh_to_type(scene_obj.get("scene_type", "叙事场景"))


def _build_storyboard(scene: dict) -> list[dict]:
    out = []
    nar = (scene.get("narration") or "").strip()
    if nar:
        out.append({"speaker": "旁白", "text": nar, "kind": "narration"})
    for d in scene.get("dialogue") or []:
        speaker = (d.get("speaker") or "").strip() or "角色"
        content = (d.get("content") or "").strip()
        if not content:
            continue
        out.append({
            "speaker": speaker, "text": content,
            "kind": "dialogue", "tone": d.get("tone", ""),
        })
    return out


def upload_file(storage, key: str, path: Path, *, dry: bool) -> str:
    if dry:
        print(f"  [DRY] would upload {path.relative_to(REPO_ROOT)} → key={key}")
        return f"dry://{key}"
    data = path.read_bytes()
    url = storage.save_bytes(key, data, content_type=_content_type_for(path))
    print(f"  ↑ {path.relative_to(REPO_ROOT)} → {url}")
    return url


def seed_global_assets(storage, story_id: str, *, dry: bool) -> None:
    g = SCENES_DIR / "global"
    if not g.exists():
        print(f"[!] no global dir at {g}")
        return
    for kind_dir, kind in (("characters", "character"), ("objects", "object")):
        base = g / kind_dir
        if not base.exists():
            continue
        for png in sorted(base.glob("*.png")):
            name = png.stem
            png_key = f"official/{story_id}/global/{kind_dir}/{name}.png"
            url = upload_file(storage, png_key, png, dry=dry)
            svg = base / f"{name}.svg"
            svg_url = None
            if svg.exists():
                svg_key = f"official/{story_id}/global/{kind_dir}/{name}.svg"
                svg_url = upload_file(storage, svg_key, svg, dry=dry)
            asset = {
                "id": f"official-{story_id}-global-{kind}-{name}",
                "name": name, "kind": kind, "url": url, "svg_url": svg_url,
                "scope": "global", "story_id": story_id,
                "is_official": True, "public": True,
            }
            if not dry:
                db.upsert_asset(asset)


def seed_scene_local_assets(storage, story_id: str, scene_dir: Path, scene_idx: int,
                             *, dry: bool) -> tuple[str | None, str | None]:
    """上传 scene-local 图片 + 录入 assets 表。返回 (comic_url, background_url)。"""
    comic_url = None
    background_url = None

    comic_png = scene_dir / "comic" / "panel.png"
    if comic_png.exists():
        comic_url = upload_file(
            storage, f"official/{story_id}/scenes/{scene_idx:03d}/comic.png",
            comic_png, dry=dry,
        )

    bg_png = scene_dir / "background" / "background.png"
    if bg_png.exists():
        background_url = upload_file(
            storage, f"official/{story_id}/scenes/{scene_idx:03d}/background.png",
            bg_png, dry=dry,
        )

    img_root = scene_dir / "image"
    if img_root.exists():
        for kind_dir, kind in (("characters", "character"), ("objects", "object")):
            base = img_root / kind_dir
            if not base.exists():
                continue
            for png in sorted(base.glob("*.png")):
                name = png.stem
                if name.endswith("_raw") or name.endswith("_transparent"):
                    # rembg 中间产物，前端用的是干净命名版本
                    continue
                key = f"official/{story_id}/scenes/{scene_idx:03d}/{kind_dir}/{name}.png"
                url = upload_file(storage, key, png, dry=dry)
                asset = {
                    "id": f"official-{story_id}-s{scene_idx:03d}-{kind}-{name}",
                    "name": name, "kind": kind, "url": url,
                    "scope": "scene", "story_id": story_id, "scene_index": scene_idx,
                    "is_official": True, "public": True,
                }
                if not dry:
                    db.upsert_asset(asset)
    return comic_url, background_url


def seed_story(storage, story_id: str, title: str, *, dry: bool) -> None:
    story_meta_path = SCENES_DIR / "story_scenes.json"
    if not story_meta_path.exists():
        print(f"[!] {story_meta_path} 不存在，跳过")
        return
    meta = _read_json(story_meta_path)
    raw_meta = {
        "story_summary": meta.get("story_summary", ""),
        "global_content": meta.get("global_content", {}),
    }

    print(f"\n=== seed story {story_id!r} ===")

    # 必须先 upsert 故事行 — scenes 表对 story_id 有 FK 约束。
    if not dry:
        db.upsert_story({
            "id": story_id,
            "title": title,
            "summary": raw_meta["story_summary"],
            "cover_url": None,  # 占位，扫完场景后更新
            "scene_count": 0,
            "status": "ready",
            "is_official": True,
            "public": True,
            "owner_user_id": None,
            "raw_meta": raw_meta,
            "likes": 512,
            "input_text": "",
        })

    seed_global_assets(storage, story_id, dry=dry)

    scenes_data: list[dict] = []
    cover_url: str | None = None
    for sd in _scene_dirs():
        idx = int(sd.name)
        scene_json = sd / "scene.json"
        if not scene_json.exists():
            continue
        scene_obj = _read_json(scene_json)
        scene_type = _scene_type(scene_obj)
        comic_url, background_url = seed_scene_local_assets(
            storage, story_id, sd, idx, dry=dry,
        )
        if cover_url is None and comic_url:
            cover_url = comic_url

        scene_row = {
            "id": f"{story_id}:{idx:03d}",
            "story_id": story_id,
            "scene_index": idx,
            "scene_type": scene_type,
            "title": scene_obj.get("event_summary") or (scene_obj.get("narration") or "")[:40],
            "narration": scene_obj.get("narration", ""),
            "interaction_goal": scene_obj.get("interaction_goal"),
            "initial_frame": scene_obj.get("initial_frame"),
            "event_outcome": scene_obj.get("event_outcome"),
            "comic_url": comic_url,
            "background_url": background_url,
            "raw_json": {
                **scene_obj,
                # 把 storyboard 也存进 raw_json 方便前端无需再拼
                "_storyboard": _build_storyboard(scene_obj),
            },
        }
        scenes_data.append(scene_row)
        if not dry:
            db.upsert_scene(scene_row)

    # 扫完所有场景后回写 cover_url + scene_count
    if dry:
        print(f"  [DRY] would upsert story {story_id!r} with {len(scenes_data)} scenes")
    else:
        db.upsert_story({
            "id": story_id,
            "title": title,
            "summary": raw_meta["story_summary"],
            "cover_url": cover_url,
            "scene_count": len(scenes_data),
            "status": "ready",
            "is_official": True,
            "public": True,
            "owner_user_id": None,
            "raw_meta": raw_meta,
            "likes": 512,
            "input_text": "",
        })
        print(f"  ✓ story upserted: {story_id} ({len(scenes_data)} scenes, cover={cover_url})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="只扫描，不上传 OSS、不写库")
    parser.add_argument("--story-id", default=DEFAULT_STORY_ID)
    parser.add_argument("--title", default=DEFAULT_TITLE)
    args = parser.parse_args()

    if not args.dry_run:
        os.environ.setdefault("MINDSHOW_STORAGE", "oss")
        kind = os.environ.get("MINDSHOW_STORAGE", "local")
        if kind != "oss":
            print(f"[!] MINDSHOW_STORAGE={kind!r}，期望 'oss'。先 export MINDSHOW_STORAGE=oss")
            return 1
        for k in ("MINDSHOW_OSS_BUCKET", "MINDSHOW_OSS_ENDPOINT",
                  "MINDSHOW_OSS_AK_ID", "MINDSHOW_OSS_AK_SECRET"):
            if not os.environ.get(k):
                print(f"[!] env {k} 未设置")
                return 1

    storage = get_storage() if not args.dry_run else None
    seed_story(storage, args.story_id, args.title, dry=args.dry_run)
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
