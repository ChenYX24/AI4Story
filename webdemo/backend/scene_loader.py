import json
from functools import lru_cache
from typing import Any

from . import asset_resolver
from .story_registry import story_json_path, story_root

NARRATIVE = "叙事场景"
INTERACTIVE = "交互场景"


@lru_cache(maxsize=16)
def _load_story_from_path(story_json: str) -> dict[str, Any]:
    with open(story_json, "r", encoding="utf-8") as f:
        return json.load(f)


def load_story(story_id: str | None = None) -> dict[str, Any]:
    return _load_story_from_path(str(story_json_path(story_id).resolve()))


def clear_story_cache(story_id: str | None = None) -> None:
    _load_story_from_path.cache_clear()


def _scene_type_en(zh: str) -> str:
    return "narrative" if zh == NARRATIVE else "interactive"


def story_summary_payload(story_id: str | None = None) -> dict[str, Any]:
    story = load_story(story_id)
    scenes_meta = []
    for s in story["scenes"]:
        idx = s["scene_index"]
        t = _scene_type_en(s["scene_type"])
        scenes_meta.append(
            {
                "index": idx,
                "type": t,
                "title": s.get("event_summary") or s.get("narration", "")[:40],
                "interaction_goal": s.get("interaction_goal") if t == "interactive" else None,
            }
        )
    g = story.get("global_content", {})
    return {
        "story_summary": story.get("story_summary", ""),
        "scene_count": len(story["scenes"]),
        "scenes": scenes_meta,
        "global_characters": [
            {"name": c["name"], "url": asset_resolver.url_for(0, "global_character", c["name"], story_id=story_id)}
            for c in g.get("characters", [])
        ],
        "global_objects": [
            {"name": o["name"], "url": asset_resolver.url_for(0, "global_object", o["name"], story_id=story_id)}
            for o in g.get("objects", [])
        ],
    }


def _load_scene_json(idx: int, story_id: str | None = None) -> dict[str, Any]:
    p = story_root(story_id) / f"{idx:03d}" / "scene.json"
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def scene_payload(idx: int, story_id: str | None = None) -> dict[str, Any]:
    scene = _load_scene_json(idx, story_id)
    t = _scene_type_en(scene["scene_type"])
    if t == "narrative":
        storyboard = _build_storyboard(scene)
        return {
            "index": idx,
            "type": "narrative",
            "summary": scene.get("event_summary", ""),
            "narration": scene.get("narration", ""),
            "comic_url": asset_resolver.url_for(idx, "comic", story_id=story_id),
            "storyboard": storyboard,
        }
    # interactive
    chars = scene.get("characters", [])
    props = scene.get("objects", [])
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
                "url": _resolve_character_url(idx, c["name"], story_id),
                "default_x": default_x,
                "default_y": 0.70,
            }
            for c, default_x in zip(chars, _evenly_spaced_x(len(chars)))
        ],
        "props": [
            {
                "name": o["name"],
                "url": _resolve_object_url(idx, o["name"], story_id),
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


def _resolve_character_url(scene_idx: int, name: str, story_id: str | None) -> str:
    scene_path = asset_resolver.path_for(scene_idx, "scene_character", name, story_id=story_id)
    if scene_path.exists():
        return asset_resolver.url_for(scene_idx, "scene_character", name, story_id=story_id)
    global_path = asset_resolver.path_for(0, "global_character", name, story_id=story_id)
    if global_path.exists():
        return asset_resolver.url_for(0, "global_character", name, story_id=story_id)
    return asset_resolver.url_for(scene_idx, "scene_character", name, story_id=story_id)


def _resolve_object_url(scene_idx: int, name: str, story_id: str | None) -> str:
    scene_path = asset_resolver.path_for(scene_idx, "scene_object", name, story_id=story_id)
    if scene_path.exists():
        return asset_resolver.url_for(scene_idx, "scene_object", name, story_id=story_id)
    global_path = asset_resolver.path_for(0, "global_object", name, story_id=story_id)
    if global_path.exists():
        return asset_resolver.url_for(0, "global_object", name, story_id=story_id)
    return asset_resolver.url_for(scene_idx, "scene_object", name, story_id=story_id)


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
        lines.append(
            {
                "speaker": speaker,
                "text": content,
                "kind": "dialogue",
                "tone": d.get("tone", ""),
            }
        )
    return lines
