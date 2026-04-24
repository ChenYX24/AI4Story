"""Per-scene suggested questions for "和讲故事的人聊聊".

The questions are grounded in the current scene's events and the overall story —
NOT in global world-building. They are generated once via Qwen and cached to
`scene.json` so subsequent reads are instant.

During custom-story creation we pre-generate these for every scene so the very
first chat open is also instant (see `ensure_scene_questions_for_story`).
"""
import json
import logging
from pathlib import Path
from typing import Any

from ..scene_loader import _load_scene_json, clear_story_cache, load_story
from ..story_registry import story_root
from .qwen_service import QwenError, call_json

log = logging.getLogger(__name__)

_FALLBACK_QUESTIONS = [
    "他为什么这么做？",
    "如果我是他，我会怎么办？",
    "可不可以换一个结局？",
]


def _scene_json_path(scene_idx: int, story_id: str | None) -> Path:
    return story_root(story_id) / f"{scene_idx:03d}" / "scene.json"


def _build_prompt(scene: dict[str, Any], story_summary: str) -> str:
    scene_type = scene.get("scene_type", "")
    chars = "、".join(c.get("name", "") for c in scene.get("characters", []) if c.get("name")) or "（无）"
    objs = "、".join(o.get("name", "") for o in scene.get("objects", []) if o.get("name")) or "（无）"
    event = scene.get("event_summary") or scene.get("narration") or scene.get("initial_frame") or ""
    goal = scene.get("interaction_goal", "")
    return (
        "你在为一个 4-6 岁儿童的互动绘本生成聊天建议问题。"
        "小朋友可以点击问题向讲故事的人提问。\n\n"
        f"【整本故事大纲】{story_summary}\n"
        f"【当前场景类型】{scene_type}\n"
        f"【当前场景】{event}\n"
        + (f"【本幕互动目标】{goal}\n" if goal else "")
        + f"【出场角色】{chars}\n"
        f"【场上物品】{objs}\n\n"
        "请围绕【当前场景】设计 3 条简短的启发式问题：\n"
        "- 紧扣这一幕刚发生/正在发生的事，不要问其它幕或超出故事的内容\n"
        "- 每条不超过 15 个字，口语化，4-6 岁小朋友能理解\n"
        "- 三条要有不同视角（例如：探究动机 / 换位思考 / 设想不同结果）\n"
        "- 不要危险/恐怖/暴力/消极词；不要反问式说教\n\n"
        '严格输出 JSON：{"questions":["问题1","问题2","问题3"]}，不要代码块或其它文字。'
    )


def _persist(scene_idx: int, story_id: str | None, questions: list[str]) -> None:
    path = _scene_json_path(scene_idx, story_id)
    if not path.exists():
        return
    try:
        scene = json.loads(path.read_text(encoding="utf-8"))
        scene["suggested_questions"] = questions
        path.write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8")
        clear_story_cache(story_id)
    except Exception as e:
        log.warning("[suggestion] persist failed for scene %s: %s", scene_idx, e)


def _clean_questions(raw: Any) -> list[str]:
    out: list[str] = []
    for q in raw or []:
        s = str(q).strip().rstrip("?？") + "？"
        if s and s != "？" and len(s) <= 30:
            out.append(s)
        if len(out) >= 3:
            break
    return out


def generate_scene_questions(scene_idx: int, story_id: str | None = None) -> list[str]:
    """Generate suggested questions via Qwen, persist to scene.json, return them.

    Falls back to a static list on any error — this endpoint must never block
    the chat UI from opening.
    """
    try:
        scene = _load_scene_json(scene_idx, story_id)
    except Exception as e:
        log.warning("[suggestion] scene load failed: %s", e)
        return list(_FALLBACK_QUESTIONS)

    try:
        story = load_story(story_id)
        story_summary = story.get("story_summary", "")
    except Exception:
        story_summary = ""

    try:
        result = call_json(_build_prompt(scene, story_summary), temperature=0.6, timeout=30)
        questions = _clean_questions(result.get("questions"))
    except QwenError as e:
        log.warning("[suggestion] Qwen failed for scene %s: %s", scene_idx, e)
        questions = []

    if len(questions) < 3:
        questions = (questions + _FALLBACK_QUESTIONS)[:3]

    _persist(scene_idx, story_id, questions)
    return questions


def get_scene_questions(scene_idx: int, story_id: str | None = None) -> list[str]:
    """Return cached suggested_questions if present; otherwise generate + cache."""
    try:
        scene = _load_scene_json(scene_idx, story_id)
        cached = scene.get("suggested_questions")
        if isinstance(cached, list) and len(cached) >= 3:
            return [str(q) for q in cached[:3]]
    except Exception:
        pass
    return generate_scene_questions(scene_idx, story_id)


def ensure_scene_questions_for_story(story_id: str) -> int:
    """Pre-generate suggested_questions for every scene in the story.

    Called from the custom-story creation pipeline so that the very first
    chat open in any scene is already instant. Returns the number of scenes
    that actually had questions generated (cache misses).
    """
    try:
        story = load_story(story_id)
    except Exception as e:
        log.warning("[suggestion] load_story failed for %s: %s", story_id, e)
        return 0

    generated = 0
    for scene_meta in story.get("scenes", []):
        idx = int(scene_meta.get("scene_index", 0))
        if idx <= 0:
            continue
        try:
            existing = _load_scene_json(idx, story_id).get("suggested_questions")
            if isinstance(existing, list) and len(existing) >= 3:
                continue
        except Exception:
            continue
        generate_scene_questions(idx, story_id)
        generated += 1
    return generated
