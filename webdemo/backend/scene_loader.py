import json
from functools import lru_cache
from typing import Any

from . import asset_resolver
from .config import SCENES_DIR, STORY_JSON

NARRATIVE = "叙事场景"
INTERACTIVE = "交互场景"


@lru_cache(maxsize=1)
def load_story() -> dict[str, Any]:
    with STORY_JSON.open("r", encoding="utf-8") as f:
        return json.load(f)


def _scene_type_en(zh: str) -> str:
    return "narrative" if zh == NARRATIVE else "interactive"


def story_summary_payload() -> dict[str, Any]:
    story = load_story()
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
            {"name": c["name"], "url": asset_resolver.url_for(0, "global_character", c["name"])}
            for c in g.get("characters", [])
        ],
        "global_objects": [
            {"name": o["name"], "url": asset_resolver.url_for(0, "global_object", o["name"])}
            for o in g.get("objects", [])
        ],
    }


def _load_scene_json(idx: int) -> dict[str, Any]:
    p = SCENES_DIR / f"{idx:03d}" / "scene.json"
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def scene_payload(idx: int) -> dict[str, Any]:
    scene = _load_scene_json(idx)
    t = _scene_type_en(scene["scene_type"])
    if t == "narrative":
        storyboard = _build_storyboard(scene)
        return {
            "index": idx,
            "type": "narrative",
            "summary": scene.get("event_summary", ""),
            "narration": scene.get("narration", ""),
            "comic_url": asset_resolver.url_for(idx, "comic"),
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
        "background_url": asset_resolver.url_for(idx, "background"),
        "characters": [
            {
                "name": c["name"],
                "url": asset_resolver.url_for(idx, "scene_character", c["name"]),
                "default_x": default_x,
                "default_y": 0.70,
            }
            for c, default_x in zip(chars, _evenly_spaced_x(len(chars)))
        ],
        "props": [
            {
                "name": o["name"],
                "url": asset_resolver.url_for(idx, "scene_object", o["name"]),
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
