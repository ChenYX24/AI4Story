import json
from functools import lru_cache
from typing import Any

from ..scene_loader import _load_scene_json
from .qwen_service import QwenError, call_json


def _fallback_layout(scene: dict[str, Any]) -> list[dict[str, Any]]:
    chars = scene.get("characters", []) or []
    objs = scene.get("objects", []) or []
    placements: list[dict[str, Any]] = []
    # characters along bottom
    if chars:
        if len(chars) == 1:
            xs = [0.5]
        else:
            xs = [0.2 + 0.6 * i / (len(chars) - 1) for i in range(len(chars))]
        for c, x in zip(chars, xs):
            placements.append(
                {"name": c["name"], "kind": "character", "x": x, "y": 0.72, "scale": 1.0, "rotation": 0.0}
            )
    # objects in a grid at top-middle
    if objs:
        cols = 3
        for i, o in enumerate(objs):
            row = i // cols
            col = i % cols
            x = 0.2 + 0.3 * col
            y = 0.25 + 0.18 * row
            placements.append(
                {"name": o["name"], "kind": "object", "x": x, "y": y, "scale": 0.9, "rotation": 0.0}
            )
    return placements


def _clamp01(v: float) -> float:
    try:
        return max(0.02, min(0.98, float(v)))
    except (TypeError, ValueError):
        return 0.5


def _build_prompt(scene: dict[str, Any]) -> str:
    chars = [
        {"name": c["name"], "pose": c.get("pose", "")}
        for c in scene.get("characters", []) or []
    ]
    objs = [
        {"name": o["name"], "description": o.get("appearance_description", "")}
        for o in scene.get("objects", []) or []
    ]
    payload = {
        "interaction_goal": scene.get("interaction_goal", ""),
        "initial_frame": scene.get("initial_frame", ""),
        "background": scene.get("background_visual_description", ""),
        "characters": chars,
        "objects": objs,
    }
    return (
        "你是儿童互动故事书的美术布局师。请根据下面的场景信息，"
        "为每个角色与物品在背景画面上规划一个合理的起始位置。\n\n"
        "坐标系：x 从 0（最左）到 1（最右）；y 从 0（最上）到 1（最下）。\n"
        "规则：\n"
        "- 角色通常站在画面下半部分 (y 在 0.55-0.85)，不要重叠。\n"
        "- 大型物品（如树、床）放在背景中后景，可稍靠上 (y 在 0.35-0.60)。\n"
        "- 小道具（如鲜花、蘑菇、蝴蝶）分散在前景和中景，避免堆叠。\n"
        "- 任何 x、y 都要在 0.05-0.95 之间，不能超出画面。\n"
        "- 如果物品是飞行/悬浮类（蝴蝶、鸟巢），y 可以较小。\n\n"
        "输出严格 JSON，结构：\n"
        '{"placements":[{"name":"名字","kind":"character"或"object",'
        '"x":0.xx,"y":0.xx,"scale":0.6-1.3,"rotation":-15到15}]}\n'
        "不要输出任何其他文字。\n\n"
        f"场景信息：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


@lru_cache(maxsize=64)
def plan_layout(scene_idx: int, story_id: str | None = None) -> tuple:
    scene = _load_scene_json(scene_idx, story_id)
    try:
        result = call_json(_build_prompt(scene), temperature=0.3, timeout=30)
        raw = result.get("placements") or []
        valid_names = {c["name"] for c in scene.get("characters", [])} | {
            o["name"] for o in scene.get("objects", [])
        }
        placements: list[dict[str, Any]] = []
        for item in raw:
            name = item.get("name")
            if name not in valid_names:
                continue
            kind = item.get("kind")
            if kind not in ("character", "object"):
                kind = "character" if any(c["name"] == name for c in scene.get("characters", [])) else "object"
            placements.append(
                {
                    "name": name,
                    "kind": kind,
                    "x": _clamp01(item.get("x", 0.5)),
                    "y": _clamp01(item.get("y", 0.5)),
                    "scale": max(0.4, min(1.5, float(item.get("scale", 1.0)))),
                    "rotation": max(-30.0, min(30.0, float(item.get("rotation", 0.0)))),
                }
            )
        # fill in missing names
        seen = {p["name"] for p in placements}
        for fb in _fallback_layout(scene):
            if fb["name"] not in seen:
                placements.append(fb)
        return tuple(tuple(sorted(p.items())) for p in placements)
    except (QwenError, Exception) as e:
        print(f"[placement_service] fallback due to: {e}")
        return tuple(tuple(sorted(p.items())) for p in _fallback_layout(scene))


def get_placements(scene_idx: int, story_id: str | None = None) -> list[dict[str, Any]]:
    return [dict(p) for p in plan_layout(scene_idx, story_id)]


def clear_layout_cache(story_id: str | None = None) -> None:
    plan_layout.cache_clear()
