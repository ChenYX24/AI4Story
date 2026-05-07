"""Story retelling (复述) service.

Generates guiding hints per scene, evaluates child's spoken retelling against
the original story, and produces an encouraging overall summary.

In-memory session store — sessions survive within the server process lifetime.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ..scene_loader import _load_scene_json, clear_story_cache, load_story
from ..story_registry import story_root
from .qwen_service import QwenError, call_json

log = logging.getLogger(__name__)

# In-memory session storage keyed by session_id.
_RETELL_SESSIONS: dict[str, "RetellSession"] = {}

_FALLBACK_HINTS = [
    "这里发生了什么故事呢？",
    "你能讲讲这一页的故事吗？",
    "你还记得这里出现了谁吗？",
]

_MIN_TEXT_LENGTH = 3


@dataclass
class RetellSceneResult:
    correctness: int = 0
    child_text: str = ""
    covered_points: list = field(default_factory=list)


@dataclass
class RetellSession:
    story_id: str
    story_title: str = ""
    story_summary: str = ""
    scenes: list = field(default_factory=list)
    results: dict = field(default_factory=dict)  # scene_index -> RetellSceneResult
    total_scenes: int = 0
    created_at: str = ""


# ── helpers ─────────────────────────────────────────────────────


def _scene_json_path(scene_idx: int, story_id: str | None) -> Path:
    return story_root(story_id) / f"{scene_idx:03d}" / "scene.json"


def _build_hint_prompt(scene: dict, story_summary: str) -> str:
    event = scene.get("narration") or scene.get("event_summary") or ""
    chars = "、".join(
        c.get("name", "") for c in scene.get("characters", []) if c.get("name")
    ) or "（无）"

    return (
        f'你在为一个 4-6 岁儿童的绘本故事设计「复述引导问题」。\n'
        f'小朋友刚读完这个故事，现在要看着画面用自己的话重新讲一遍。\n'
        f'你的问题是给小朋友一个温和的提示，引导他回忆并讲出这一页的内容。\n\n'
        f'【故事大纲】{story_summary}\n'
        f'【本页内容】{event}\n'
        f'【出场角色】{chars}\n\n'
        f'要求：\n'
        f'- 提出 1 个开放式问题，引导小朋友用自己的话描述这页发生的事\n'
        f'- 问题简短（不超过 20 个字），口语化，4-6 岁能理解\n'
        f'- 语气温暖鼓励，让小朋友愿意开口说\n\n'
        f'严格输出 JSON：{{"question":"你的问题"}}，不要代码块或其它文字。'
    )


def _generate_hint(scene_idx: int, story_id: str | None, scene: dict, story_summary: str) -> str:
    """Generate a hint question for one scene. Cache in scene.json like suggestion_service."""
    # check cache
    try:
        cached = _load_scene_json(scene_idx, story_id).get("retell_hint")
        if isinstance(cached, str) and cached.strip():
            return cached
    except Exception:
        pass

    try:
        result = call_json(_build_hint_prompt(scene, story_summary), temperature=0.6, timeout=30)
        question = str(result.get("question", "")).strip()
    except QwenError as e:
        log.warning("[retell] hint generation failed for scene %s: %s", scene_idx, e)
        question = ""

    if not question:
        question = _FALLBACK_HINTS[(scene_idx - 1) % len(_FALLBACK_HINTS)]

    # persist to scene.json
    path = _scene_json_path(scene_idx, story_id)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["retell_hint"] = question
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            clear_story_cache(story_id)
        except Exception as e:
            log.warning("[retell] hint persist failed for scene %s: %s", scene_idx, e)

    return question


def _build_comparison_prompt(scene_text: str, child_text: str) -> str:
    return (
        f'你是一位温暖耐心的幼儿园老师，正在听一个 4-6 岁的小朋友复述绘本故事。\n\n'
        f'【这一页的原文内容】{scene_text}\n\n'
        f'【小朋友的复述】{child_text}\n\n'
        f'请评估小朋友的复述，并严格输出以下 JSON：\n'
        f'{{\n'
        f'  "correctness": 数字(0-100, 表示覆盖了多少原文要点),\n'
        f'  "covered_points": ["小朋友说对了什么", ...],\n'
        f'  "missed_points": ["小朋友漏掉了什么重要内容", ...],\n'
        f'  "encouragement": "温暖的鼓励话语，先说小朋友做得好的地方",\n'
        f'  "suggestion": "温和的引导，帮小朋友想起漏掉的内容（如果都说对了就说继续加油之类的话）"\n'
        f'}}\n\n'
        f'重要规则：\n'
        f'- 面对的是 4-6 岁小朋友，永远不要批评或说负面的话\n'
        f'- 哪怕小朋友说的和原文完全不一样，也要先认可他愿意开口说的勇气\n'
        f'- encouragement 必须温暖、具体，指出至少一个闪光点\n'
        f'- missed_points 写成"还可以补充"的角度，不说"错了"或"没记住"\n'
        f'- 所有文字用中文，适合念给小朋友听'
    )


def _build_summary_prompt(results: list[dict], story_summary: str, story_title: str) -> str:
    scenes_text = "\n".join(
        f"第{r['scene_index']}页：正确度{r['correctness']}%，"
        f"小朋友说「{r['child_text']}」，"
        f"覆盖要点：{'、'.join(r['covered_points'])}"
        for r in results
    )

    return (
        f'你是一位温暖耐心的幼儿园老师，正在总结一个 4-6 岁小朋友的绘本复述表现。\n\n'
        f'【故事名称】{story_title}\n'
        f'【故事大意】{story_summary}\n'
        f'【小朋友各页表现】\n{scenes_text}\n\n'
        f'请评估小朋友的复述表现，并严格输出以下 JSON：\n'
        f'{{\n'
        f'  "overall_score": 数字(0-100),\n'
        f'  "star_count": 数字(1-5, 根据 overall_score: >=90→5, >=70→4, >=50→3, >=30→2, <30→1),\n'
        f'  "badge": "一个可爱的称号，如故事小达人、记忆小高手、勇敢表达家等",\n'
        f'  "strengths": ["优点1", "优点2"],\n'
        f'  "growth_areas": ["可以继续加油的地方1", "可以继续加油的地方2"],\n'
        f'  "encouragement_summary": "一段温暖的总评寄语，鼓励小朋友继续阅读和讲故事（不超过80字）"\n'
        f'}}\n\n'
        f'重要规则：\n'
        f'- 永远保持温暖鼓励的语气，绝不批评\n'
        f'- 优点要多写，成长空间要用积极正面的方式表达\n'
        f'- 适合家长念给小朋友听的语气'
    )


# ── public API ──────────────────────────────────────────────────


def start_session(story_id: str, session_id: str | None = None) -> dict:
    """Load story, generate hints for each scene, create/return session."""
    if session_id and session_id in _RETELL_SESSIONS:
        sess = _RETELL_SESSIONS[session_id]
    else:
        try:
            story = load_story(story_id)
        except FileNotFoundError:
            raise
        except Exception as e:
            log.warning("[retell] load_story failed: %s", e)
            raise RuntimeError(f"无法加载故事: {e}") from e

        story_summary = story.get("story_summary", "")
        story_title = story.get("story_title", "") or story.get("story_summary", "")[:30]
        scenes_meta = story.get("scenes", [])

        sid = session_id or f"ret_{uuid.uuid4().hex[:12]}"
        sess = RetellSession(
            story_id=story_id,
            story_title=story_title,
            story_summary=story_summary,
            total_scenes=len(scenes_meta),
            created_at="",
        )

        for meta in scenes_meta:
            idx = int(meta.get("scene_index", 0))
            if idx <= 0:
                continue
            try:
                scene = _load_scene_json(idx, story_id)
            except Exception:
                scene = {}

            scene_type = scene.get("scene_type", meta.get("scene_type", "narrative"))
            hint = _generate_hint(idx, story_id, scene, story_summary)

            from ..asset_resolver import url_for

            comic_url = ""
            try:
                comic_url = url_for(idx, "comic", "panel.png", story_id)
            except Exception:
                pass

            sess.scenes.append({
                "scene_index": idx,
                "type": scene_type,
                "comic_url": comic_url,
                "summary": scene.get("summary") or scene.get("event_summary", ""),
                "narration": scene.get("narration", ""),
                "hint_question": hint,
            })

        _RETELL_SESSIONS[sid] = sess

    return {
        "session_id": sid,
        "story_title": sess.story_title,
        "total_scenes": sess.total_scenes,
        "scenes": sess.scenes,
    }


def evaluate_submission(session_id: str, scene_index: int, child_text: str) -> dict:
    """Compare child's retelling with original scene text, return encouraging feedback."""
    if not child_text.strip() or len(child_text.strip()) < _MIN_TEXT_LENGTH:
        raise ValueError("child_text too short")

    sess = _RETELL_SESSIONS.get(session_id)
    if not sess:
        raise KeyError(f"session {session_id} not found")

    # find scene data
    scene_text = ""
    try:
        scene = _load_scene_json(scene_index, sess.story_id)
        scene_text = (scene.get("narration") or scene.get("event_summary") or "").strip()
    except Exception:
        pass

    if not scene_text:
        # fallback: use story summary as context
        scene_text = sess.story_summary

    try:
        result = call_json(_build_comparison_prompt(scene_text, child_text), temperature=0.5, timeout=60)
    except QwenError as e:
        log.warning("[retell] call_json failed for scene %s: %s", scene_index, e)
        # graceful fallback when AI call fails
        result = {
            "correctness": 50,
            "covered_points": ["勇敢地讲出了自己的想法"],
            "missed_points": [],
            "encouragement": f"你讲得很认真！虽然出了点小问题，但老师看到你在努力回忆故事。",
            "suggestion": "要不要再看看图片，想一想发生了什么？",
        }

    feedback = {
        "recognized_text": child_text,
        "correctness": max(0, min(100, int(result.get("correctness", 50)))),
        "covered_points": [str(p) for p in result.get("covered_points", []) if p],
        "missed_points": [str(p) for p in result.get("missed_points", []) if p],
        "encouragement": str(result.get("encouragement", "你讲得真棒！")),
        "suggestion": str(result.get("suggestion", "再看看图片，试着讲一讲？")),
    }

    # store result
    sess.results[scene_index] = RetellSceneResult(
        correctness=feedback["correctness"],
        child_text=child_text,
        covered_points=feedback["covered_points"],
    )

    return {"feedback": feedback}


def build_summary(session_id: str) -> dict:
    """Aggregate all scene results into overall evaluation."""
    sess = _RETELL_SESSIONS.get(session_id)
    if not sess:
        raise KeyError(f"session {session_id} not found")

    results = [
        {
            "scene_index": idx,
            "correctness": r.correctness,
            "child_text": r.child_text,
            "covered_points": r.covered_points,
        }
        for idx, r in sorted(sess.results.items())
    ]

    if not results:
        return {
            "overall_score": 0,
            "star_count": 0,
            "badge": "小小故事家",
            "strengths": [],
            "growth_areas": [],
            "encouragement_summary": "你还没有复述任何一页，快去试试吧！",
            "scene_results": [],
        }

    try:
        raw = call_json(
            _build_summary_prompt(results, sess.story_summary, sess.story_title),
            temperature=0.5,
            timeout=60,
        )
    except QwenError as e:
        log.warning("[retell] summary call_json failed: %s", e)
        # fallback computation
        avg = sum(r["correctness"] for r in results) // max(len(results), 1)
        star_count = 5 if avg >= 90 else 4 if avg >= 70 else 3 if avg >= 50 else 2 if avg >= 30 else 1
        raw = {
            "overall_score": avg,
            "star_count": star_count,
            "badge": "故事小达人",
            "strengths": ["勇敢地讲完了整个故事"],
            "growth_areas": ["下次可以试着讲更多细节"],
            "encouragement_summary": f"你把故事从头到尾讲了一遍，真是太厉害了！继续加油，你会越来越棒的！",
        }

    return {
        "overall_score": max(0, min(100, int(raw.get("overall_score", 50)))),
        "star_count": max(1, min(5, int(raw.get("star_count", 3)))),
        "badge": str(raw.get("badge", "故事小达人")),
        "strengths": [str(s) for s in raw.get("strengths", []) if s],
        "growth_areas": [str(g) for g in raw.get("growth_areas", []) if g],
        "encouragement_summary": str(raw.get("encouragement_summary", "你真棒！")),
        "scene_results": results,
    }
