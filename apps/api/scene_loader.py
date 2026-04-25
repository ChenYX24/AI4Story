"""
故事 + 场景加载层。

数据源优先级：
  1. 数据库（stories / scenes / assets 三张表 — 由 scripts/seed_official.py 录入官方故事，
     或者由用户 stories CRUD 写入）
  2. 文件系统回落（scenes/ 目录、custom story 工作区） — 仅本地未录入数据库时使用，
     便于本地开发不依赖 OSS。

返回 payload shape 在两种数据源下保持一致，前端无感。
"""
import json
from functools import lru_cache
from typing import Any, Optional

from . import asset_resolver, db
from .story_registry import (
    DEFAULT_STORY_ID,
    is_default_story,
    story_json_path,
    story_root,
)

NARRATIVE = "叙事场景"
INTERACTIVE = "交互场景"


# ---------- 内部：从 DB 取整本故事 ----------

def _story_from_db(story_id: str) -> Optional[dict]:
    row = db.get_story(story_id)
    if not row:
        return None
    scenes = db.list_scenes(story_id)
    if not scenes:
        return None
    return {"story": row, "scenes": scenes}


# ---------- 内部：从文件系统取整本故事（回落） ----------

@lru_cache(maxsize=16)
def _load_story_from_path(story_json: str) -> dict[str, Any]:
    with open(story_json, "r", encoding="utf-8") as f:
        return json.load(f)


def load_story(story_id: str | None = None) -> dict[str, Any]:
    """
    返回原 story_scenes.json 形态。供旧路径兼容（如 narrative_generator）。
    新代码请走 story_summary_payload / scene_payload。
    """
    sid = story_id or DEFAULT_STORY_ID
    fs = _from_fs_or_none(sid)
    if fs is not None:
        return fs
    cached = _story_from_db(sid)
    if cached:
        # 把 DB 数据转成原 json 形态（仅供 narrative_generator 等老调用方）
        return _db_to_legacy_story(cached)
    raise FileNotFoundError(f"story {sid!r} not found in DB or filesystem")


def _from_fs_or_none(story_id: str) -> Optional[dict[str, Any]]:
    p = story_json_path(story_id)
    if not p.exists():
        return None
    return _load_story_from_path(str(p.resolve()))


def _db_to_legacy_story(payload: dict) -> dict:
    story = payload["story"]
    scenes = payload["scenes"]
    return {
        "story_summary": story.get("summary", ""),
        "global_content": (story.get("raw_meta") or {}).get("global_content", {}),
        "scenes": [s.get("raw_json", {}) for s in scenes],
    }


def clear_story_cache(story_id: str | None = None) -> None:
    _load_story_from_path.cache_clear()


def _scene_type_en(zh_or_en: str) -> str:
    if zh_or_en in ("narrative", "interactive", "dynamic"):
        return zh_or_en
    return "narrative" if zh_or_en == NARRATIVE else "interactive"


# ---------- 公共 API：summary ----------

def story_summary_payload(story_id: str | None = None) -> dict[str, Any]:
    sid = story_id or DEFAULT_STORY_ID

    # DB 优先
    dbp = _story_from_db(sid)
    if dbp:
        return _summary_from_db(dbp)

    # 文件系统回落
    story = load_story(sid)
    scenes_meta = []
    for s in story["scenes"]:
        idx = s["scene_index"]
        t = _scene_type_en(s["scene_type"])
        scenes_meta.append({
            "index": idx,
            "type": t,
            "title": s.get("event_summary") or s.get("narration", "")[:40],
            "interaction_goal": s.get("interaction_goal") if t == "interactive" else None,
        })
    g = story.get("global_content", {})
    return {
        "story_summary": story.get("story_summary", ""),
        "scene_count": len(story["scenes"]),
        "scenes": scenes_meta,
        "global_characters": [
            {"name": c["name"], "url": asset_resolver.url_for(0, "global_character", c["name"], story_id=sid)}
            for c in g.get("characters", [])
        ],
        "global_objects": [
            {"name": o["name"], "url": asset_resolver.url_for(0, "global_object", o["name"], story_id=sid)}
            for o in g.get("objects", [])
        ],
    }


def _summary_from_db(payload: dict) -> dict:
    story = payload["story"]
    scenes = payload["scenes"]
    sid = story["id"]
    scene_meta = []
    for s in scenes:
        scene_meta.append({
            "index": s["scene_index"],
            "type": _scene_type_en(s["scene_type"]),
            "title": s.get("title") or "",
            "interaction_goal": s.get("interaction_goal") if s["scene_type"] == "interactive" else None,
        })
    chars = db.list_assets(scope="global", story_id=sid)
    return {
        "story_summary": story.get("summary", ""),
        "scene_count": len(scenes),
        "scenes": scene_meta,
        "global_characters": [{"name": a["name"], "url": a["url"]} for a in chars if a["kind"] == "character"],
        "global_objects": [{"name": a["name"], "url": a["url"]} for a in chars if a["kind"] == "object"],
    }


# ---------- 公共 API：scene ----------

def scene_payload(idx: int, story_id: str | None = None) -> dict[str, Any]:
    sid = story_id or DEFAULT_STORY_ID

    # DB 优先
    dbp = _story_from_db(sid)
    if dbp:
        scene = next((s for s in dbp["scenes"] if s["scene_index"] == idx), None)
        if scene:
            return _scene_payload_from_db(sid, scene)
        # 故事在 DB 但场景缺失 → 落回文件系统
    return _scene_payload_from_fs(idx, sid)


def _scene_payload_from_db(story_id: str, scene: dict) -> dict:
    raw = scene.get("raw_json") or {}
    t = _scene_type_en(scene["scene_type"])
    if t == "narrative":
        storyboard = raw.get("_storyboard") or _build_storyboard(raw)
        return {
            "index": scene["scene_index"],
            "type": "narrative",
            "summary": raw.get("event_summary") or scene.get("title", ""),
            "narration": scene.get("narration", ""),
            "comic_url": scene.get("comic_url") or "",
            "storyboard": storyboard,
        }
    chars_raw = raw.get("characters", []) or []
    props_raw = raw.get("objects", []) or []
    char_assets = [_resolve_asset_db(story_id, scene["scene_index"], c["name"], "character") for c in chars_raw]
    prop_assets = [_resolve_asset_db(story_id, scene["scene_index"], o["name"], "object") for o in props_raw]
    return {
        "index": scene["scene_index"],
        "type": "interactive",
        "interaction_goal": scene.get("interaction_goal") or raw.get("interaction_goal", ""),
        "initial_frame": scene.get("initial_frame") or raw.get("initial_frame", ""),
        "event_outcome": scene.get("event_outcome") or raw.get("event_outcome", ""),
        "narration": scene.get("narration", ""),
        "background_url": scene.get("background_url") or "",
        "characters": [
            {
                "name": c["name"],
                "url": (a or {}).get("url") or "",
                "default_x": default_x,
                "default_y": 0.70,
            }
            for c, a, default_x in zip(chars_raw, char_assets, _evenly_spaced_x(len(chars_raw)))
        ],
        "props": [
            {
                "name": o["name"],
                "url": (a or {}).get("url") or "",
                "description": o.get("appearance_description", ""),
            }
            for o, a in zip(props_raw, prop_assets)
        ],
    }


def _resolve_asset_db(story_id: str, scene_idx: int, name: str, kind: str) -> Optional[dict]:
    return db.find_scene_asset(story_id, scene_idx, name, kind)


def _scene_payload_from_fs(idx: int, story_id: str) -> dict:
    p = story_root(story_id) / f"{idx:03d}" / "scene.json"
    with p.open("r", encoding="utf-8") as f:
        scene = json.load(f)
    t = _scene_type_en(scene["scene_type"])
    if t == "narrative":
        return {
            "index": idx,
            "type": "narrative",
            "summary": scene.get("event_summary", ""),
            "narration": scene.get("narration", ""),
            "comic_url": asset_resolver.url_for(idx, "comic", story_id=story_id),
            "storyboard": _build_storyboard(scene),
        }
    chars = scene.get("characters", []) or []
    props = scene.get("objects", []) or []
    return {
        "index": idx,
        "type": "interactive",
        "interaction_goal": scene.get("interaction_goal", ""),
        "initial_frame": scene.get("initial_frame", ""),
        "event_outcome": scene.get("event_outcome", ""),
        "narration": scene.get("narration", ""),
        "background_url": asset_resolver.url_for(idx, "background", story_id=story_id),
        "characters": [
            {
                "name": c["name"],
                "url": _resolve_character_url_fs(idx, c["name"], story_id),
                "default_x": default_x,
                "default_y": 0.70,
            }
            for c, default_x in zip(chars, _evenly_spaced_x(len(chars)))
        ],
        "props": [
            {
                "name": o["name"],
                "url": _resolve_object_url_fs(idx, o["name"], story_id),
                "description": o.get("appearance_description", ""),
            }
            for o in props
        ],
    }


def _evenly_spaced_x(n: int) -> list[float]:
    if n <= 0:
        return []
    if n == 1:
        return [0.5]
    return [0.2 + 0.6 * i / (n - 1) for i in range(n)]


def _resolve_character_url_fs(scene_idx: int, name: str, story_id: str | None) -> str:
    scene_path = asset_resolver.path_for(scene_idx, "scene_character", name, story_id=story_id)
    if scene_path.exists():
        return asset_resolver.url_for(scene_idx, "scene_character", name, story_id=story_id)
    global_path = asset_resolver.path_for(0, "global_character", name, story_id=story_id)
    if global_path.exists():
        return asset_resolver.url_for(0, "global_character", name, story_id=story_id)
    return asset_resolver.url_for(scene_idx, "scene_character", name, story_id=story_id)


def _resolve_object_url_fs(scene_idx: int, name: str, story_id: str | None) -> str:
    scene_path = asset_resolver.path_for(scene_idx, "scene_object", name, story_id=story_id)
    if scene_path.exists():
        return asset_resolver.url_for(scene_idx, "scene_object", name, story_id=story_id)
    global_path = asset_resolver.path_for(0, "global_object", name, story_id=story_id)
    if global_path.exists():
        return asset_resolver.url_for(0, "global_object", name, story_id=story_id)
    return asset_resolver.url_for(scene_idx, "scene_object", name, story_id=story_id)


def _load_scene_json(idx: int, story_id: str | None = None) -> dict[str, Any]:
    """老接口：narrative_generator 仍然在用。优先 DB，回落文件系统。"""
    sid = story_id or DEFAULT_STORY_ID
    dbp = _story_from_db(sid)
    if dbp:
        scene = next((s for s in dbp["scenes"] if s["scene_index"] == idx), None)
        if scene:
            return scene.get("raw_json") or {}
    p = story_root(sid) / f"{idx:03d}" / "scene.json"
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _build_storyboard(scene: dict[str, Any]) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    narration = (scene.get("narration") or "").strip()
    if narration:
        lines.append({"speaker": "旁白", "text": narration, "kind": "narration"})
    for d in scene.get("dialogue", []) or []:
        speaker = d.get("speaker", "").strip() or "角色"
        content = (d.get("content") or "").strip()
        if not content:
            continue
        lines.append({
            "speaker": speaker,
            "text": content,
            "kind": "dialogue",
            "tone": d.get("tone", ""),
        })
    return lines
