import io
import json
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

log = logging.getLogger(__name__)

from ..asset_resolver import path_for, resolve_interactive_asset
from ..config import (
    ARK_API_KEY,
    OUTPUTS_ROOT,
    PROJECT_ROOT,
    SEEDREAM_MODEL,
    SEEDREAM_PROVIDER,
    SEEDREAM_SIZE,
    SEEDREAM_TIMEOUT,
)
from ..models import CustomProp, InteractRequest, Operation, Transform
from ..scene_loader import _load_scene_json, load_story
from ..storage import get_storage
from .qwen_service import QwenError, call_json

sys.path.insert(0, str(PROJECT_ROOT))
from scripts.image_generation.seedream_client import generate_image_bytes  # noqa: E402
from scripts.workflow.story_asset_workflow import (  # noqa: E402
    build_narrative_comic_prompt,
    create_reference_board,
)

THUMB_SIZE = 256


def _format_ops(ops: list[Operation]) -> list[str]:
    lines: list[str] = []
    for i, op in enumerate(ops, 1):
        if op.subject and op.target:
            lines.append(f"{i}. 让「{op.subject}」对「{op.target}」：{op.action}")
        elif op.subject and not op.target:
            lines.append(f"{i}. 让「{op.subject}」：{op.action}")
        else:
            lines.append(f"{i}. 场景事件：{op.action}")
    return lines


def _build_qwen_prompt(
    scene: dict[str, Any],
    story_summary: str,
    ops: list[Operation],
    active_characters: list[str],
    active_objects: list[str],
    custom_props: list[CustomProp],
    all_characters: list[dict[str, Any]] | None = None,
    next_scene: dict[str, Any] | None = None,
) -> str:
    op_lines = "\n".join(_format_ops(ops)) or "（没有具体操作，只是场景的自然发展）"
    custom_str = "、".join(p.name for p in custom_props) or "（无）"

    char_notes = "\n".join(
        f"  - {c.get('name', '')}：{c.get('appearance_description', '')}"
        for c in (all_characters or [])
    ) or "  （无额外角色信息）"

    next_scene_hint = ""
    if next_scene:
        ns = (next_scene.get("event_summary") or next_scene.get("narration") or "").strip()
        if ns:
            next_scene_hint = (
                f"\n【下一幕故事走向】{ns[:80]}\n"
                "（第4格画面必须为这个转变做自然铺垫，让两幕之间丝滑衔接）"
            )

    return (
        "你是一位儿童绘本的故事编剧，正在根据孩子的互动实时扩展故事。\n"
        "请生成一个新的叙事场景，内容要紧贴孩子安排的互动，风格温暖友善，适合 5 岁儿童。\n\n"
        f"【整本故事大纲】{story_summary}\n"
        f"【上一幕交互目标】{scene.get('interaction_goal', '')}\n"
        f"【上一幕初始画面】{scene.get('initial_frame', '')}\n"
        f"【已出现的角色及造型】\n{char_notes}\n"
        f"【已出现的物品】{'、'.join(active_objects) or '（无）'}\n"
        f"【小朋友新创造的物品】{custom_str}\n\n"
        f"【小朋友安排的互动序列】\n{op_lines}"
        f"{next_scene_hint}\n\n"
        "⚠️ 角色立场约束（必须严格遵守）：\n"
        "- 每个角色都有自己的立场和性格，绝对不能随意改变\n"
        "- 反派角色（如大灰狼）永远不会主动保护或帮助主角，始终维持其阴谋动机\n"
        "- 角色的对话和行为必须与其在故事中的身份、动机一致\n"
        "- 不是所有角色都会顺着孩子的想法——保持故事张力\n\n"
        "请严格输出 JSON（不要包含任何解释或代码块标记），结构如下：\n"
        "{\n"
        '  "summary": "1 句话总结这一幕发生了什么（30 字内）",\n'
        '  "narration": "2-3 句整体旁白（100 字内），口语化、有画面感",\n'
        '  "dialogue": [\n'
        '    {"speaker":"角色名","content":"对话内容","tone":"语气"}\n'
        '  ],\n'
        '  "storyboard_panels": [\n'
        '    {\n'
        '      "panel": 1,\n'
        '      "description": "左上画面视觉描述：明确谁在哪里做什么、表情姿态（50字内）",\n'
        '      "caption": "此格旁白（15字内，口语化）",\n'
        '      "dialogue": [{"speaker":"角色名","content":"台词（10字内）","tone":"语气"}]\n'
        '    },\n'
        '    {\n'
        '      "panel": 2, "description": "右上画面描述（50字内）",\n'
        '      "caption": "旁白（15字内）", "dialogue": []\n'
        '    },\n'
        '    {\n'
        '      "panel": 3, "description": "左下画面描述（50字内）",\n'
        '      "caption": "旁白（15字内）", "dialogue": []\n'
        '    },\n'
        '    {\n'
        '      "panel": 4,\n'
        '      "description": "右下画面：展示这幕结果，并为下一幕做视觉衔接（50字内）",\n'
        '      "caption": "旁白（15字内，带入下一段故事氛围）",\n'
        '      "dialogue": []\n'
        '    }\n'
        "  ]\n"
        "}\n"
        "要求：\n"
        "- 四格漫画按时间顺序：起因→发展→转折→结果/衔接\n"
        "- 每格画面和旁白必须紧扣孩子的选择，让孩子的决定真正改变故事走向\n"
        "- 第4格必须自然过渡到下一幕，不要突兀跳跃\n"
        "- 角色对话控制在每格0-2句，且符合角色性格立场\n"
        "- 不要出现危险/恐怖/暴力等不适合儿童的内容"
    )


def _collect_reference_paths(
    req: InteractRequest,
    scene_chars: list[str],
) -> list[Path]:
    """Background + global character PNGs + objects currently placed on the canvas.

    Only objects that have been dragged onto the interactive stage are used as
    reference images — inventory-only items (including user-created custom props
    still sitting in the shelf) are intentionally excluded so the next-scene comic
    only recalls what the child actually brought into play.
    """
    paths: list[Path] = []
    seen: set[Path] = set()

    # background
    bg = path_for(req.scene_idx, "background", story_id=req.story_id)
    if bg.exists():
        paths.append(bg)
        seen.add(bg)

    # global characters (full body, transparent) for all active scene chars
    for name in scene_chars:
        gc = path_for(req.scene_idx, "global_character", name, story_id=req.story_id)
        if gc.exists() and gc not in seen:
            paths.append(gc)
            seen.add(gc)

    # Objects ON the canvas only. Handles both scene-defined objects and
    # user-created custom props — the distinguishing signal is Transform.custom_url
    # (set when a custom prop was dragged in) or a name match into req.custom_props.
    custom_prop_by_name = {cp.name: cp for cp in req.custom_props}
    for pl in req.placements:
        if pl.kind != "object":
            continue
        custom_url = pl.custom_url or (
            custom_prop_by_name[pl.name].url if pl.name in custom_prop_by_name else None
        )
        if custom_url:
            rel = custom_url.lstrip("/")
            candidate = (PROJECT_ROOT / rel).resolve()
            if candidate.exists() and candidate not in seen:
                paths.append(candidate)
                seen.add(candidate)
            continue
        try:
            p = resolve_interactive_asset(
                req.scene_idx, pl.name, pl.kind, story_id=req.story_id
            )
        except FileNotFoundError:
            continue
        if p not in seen:
            paths.append(p)
            seen.add(p)

    return paths


def _storyboard_from_panels(panels: list[dict[str, Any]]) -> str:
    head = "根据当前的 event summary 设计一组漫画，整体风格为彩铅手绘风格，童趣可爱，按照田字格分隔四格漫画分镜构图，适用于儿童绘本。"
    labels = ["画面一（左上）", "画面二（右上）", "画面三（左下）", "画面四（右下）"]
    lines = [head]
    for idx, label in enumerate(labels):
        panel = panels[idx] if idx < len(panels) else {}
        desc = str(panel.get("description", "")).strip()
        caption = str(panel.get("caption", "")).strip()
        dlg = panel.get("dialogue") or []
        lines.append(f"{label}：")
        lines.append(f"画面描述：{desc}")
        if caption:
            lines.append(f"旁白文字：{caption}")
        for d in dlg:
            spk = str(d.get("speaker", "")).strip()
            txt = str(d.get("content", "")).strip()
            if spk and txt:
                lines.append(f"对话：{spk}说「{txt}」")
    return "\n".join(lines)


def _build_storyboard_lines(panels: list[dict[str, Any]], narration: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []

    has_panel_content = any(
        str(p.get("caption", "")).strip() or p.get("dialogue")
        for p in panels
    )

    if not has_panel_content:
        if narration.strip():
            lines.append({"speaker": "旁白", "text": narration.strip(), "kind": "narration", "tone": ""})
        return lines

    for panel in panels[:4]:
        caption = str(panel.get("caption", "")).strip()
        dlg = panel.get("dialogue") or []
        if caption:
            lines.append({"speaker": "旁白", "text": caption, "kind": "narration", "tone": ""})
        for d in dlg:
            content = str(d.get("content", "")).strip()
            if not content:
                continue
            lines.append({
                "speaker": str(d.get("speaker", "")).strip() or "角色",
                "text": content,
                "kind": "dialogue",
                "tone": str(d.get("tone", "")),
            })
    return lines


def _write_thumb(src: Path, dst: Path) -> None:
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((THUMB_SIZE, THUMB_SIZE))
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst, format="JPEG", quality=85)


def generate_dynamic_node(req: InteractRequest) -> dict[str, Any]:
    t0 = time.time()
    scene = _load_scene_json(req.scene_idx, req.story_id)
    story = load_story(req.story_id)
    story_summary = story.get("story_summary", "")

    scene_char_names = [c["name"] for c in scene.get("characters", [])]
    scene_obj_names = [o["name"] for o in scene.get("objects", [])]

    # On-canvas filters: only objects / custom props actually dragged onto the
    # interactive stage should flow into any downstream prompt or reference image.
    placed_object_names = {
        pl.name for pl in req.placements if pl.kind == "object" and pl.name
    }
    placed_scene_obj_names = [n for n in scene_obj_names if n in placed_object_names]
    placed_custom_props = [cp for cp in req.custom_props if cp.name in placed_object_names]
    placed_scene_objects = [
        o for o in scene.get("objects", []) if o.get("name") in placed_object_names
    ]

    all_characters = story.get("global_content", {}).get("characters", [])
    all_scenes = story.get("scenes", [])
    next_scene = next(
        (s for s in all_scenes if s.get("scene_index") == req.scene_idx + 1), None
    )

    # 1) Qwen: narrative content
    log.info("[interact] step 1/3: calling Qwen for narrative text …")
    qwen_prompt = _build_qwen_prompt(
        scene=scene,
        story_summary=story_summary,
        ops=req.ops,
        active_characters=scene_char_names,
        active_objects=placed_scene_obj_names,
        custom_props=placed_custom_props,
        all_characters=all_characters,
        next_scene=next_scene,
    )
    try:
        result = call_json(qwen_prompt, temperature=0.6, timeout=120)
    except QwenError as e:
        log.error("[interact] Qwen failed after %.1fs: %s", time.time() - t0, e)
        raise RuntimeError(f"故事文本生成失败：{e}") from e
    t1 = time.time()
    log.info("[interact] step 1 done in %.1fs", t1 - t0)

    summary = str(result.get("summary", "")).strip() or "小朋友继续推进了故事。"
    narration = str(result.get("narration", "")).strip() or summary
    panels = result.get("storyboard_panels") or []
    # prefer top-level dialogue; fall back to aggregating from panels
    top_dialogue = result.get("dialogue") or []
    dialogue: list[dict[str, Any]] = list(top_dialogue) if isinstance(top_dialogue, list) else []
    if not dialogue:
        for p in panels:
            for d in (p.get("dialogue") or []):
                if d.get("content"):
                    dialogue.append(d)

    # 2) Seedream: 4-panel comic
    storyboard_text = _storyboard_from_panels(panels)
    ref_paths = _collect_reference_paths(req, scene_char_names)
    log.info("[interact] step 2/3: building reference board from %d images …", len(ref_paths))

    node_id = f"dyn-{uuid.uuid4().hex[:10]}"
    out_dir = OUTPUTS_ROOT / req.session_id / "dynamic" / node_id
    out_dir.mkdir(parents=True, exist_ok=True)

    ref_board: Path | None = None
    if ref_paths:
        ref_board = create_reference_board(ref_paths, out_dir / "_refboard.png", cell_size=512)

    pseudo_scene = {
        "event_summary": summary,
        "narration": narration,
        "background_visual_description": scene.get("background_visual_description", ""),
        "characters": scene.get("characters", []),
        # Only props on the interactive stage are described to Seedream — mirrors
        # the reference-image filter so the text prompt cannot reintroduce
        # inventory-only items.
        "objects": [
            {"name": cp.name, "appearance_description": f"小朋友创作的「{cp.name}」"}
            for cp in placed_custom_props
        ]
        + placed_scene_objects,
        "dialogue": dialogue if isinstance(dialogue, list) else [],
    }
    seed_prompt = build_narrative_comic_prompt(pseudo_scene, storyboard_text)
    t2 = time.time()
    log.info("[interact] step 2 done in %.1fs, prompt length=%d chars", t2 - t1, len(seed_prompt))

    log.info("[interact] step 3/3: calling Seedream (model=%s, size=%s, ref_board=%s) …",
             SEEDREAM_MODEL, SEEDREAM_SIZE, "yes" if ref_board else "no")
    try:
        img_bytes = generate_image_bytes(
            api_key=ARK_API_KEY,
            prompt=seed_prompt,
            size=SEEDREAM_SIZE,
            model=SEEDREAM_MODEL,
            provider=SEEDREAM_PROVIDER,
            reference_images=[ref_board] if ref_board else None,
            timeout=SEEDREAM_TIMEOUT,
        )
    except Exception as e:
        import traceback
        print(f"[interact] Seedream FAILED after {time.time() - t2:.1f}s", flush=True)
        print(f"[interact] error type: {type(e).__name__}", flush=True)
        print(f"[interact] error detail: {e}", flush=True)
        traceback.print_exc()
        raise RuntimeError(f"四格漫画生成失败：{e}") from e
    t3 = time.time()
    log.info("[interact] step 3 done in %.1fs, image size=%d bytes", t3 - t2, len(img_bytes))

    # 始终先落本地 OUTPUTS_ROOT — node.json / refboard 还需要本地路径调试。
    panel_path = out_dir / "panel.png"
    panel_path.write_bytes(img_bytes)
    thumb_path = out_dir / "thumb.jpg"
    _write_thumb(panel_path, thumb_path)
    # 然后通过 storage backend 拿到对外可访问的 URL（MinIO 模式会另写一份到对象存储）
    storage = get_storage()
    panel_key = f"{req.session_id}/dynamic/{node_id}/panel.png"
    thumb_key = f"{req.session_id}/dynamic/{node_id}/thumb.jpg"
    panel_url = storage.save_bytes(panel_key, img_bytes, content_type="image/png")
    try:
        thumb_url = storage.save_bytes(thumb_key, thumb_path.read_bytes(), content_type="image/jpeg")
    except Exception:
        thumb_url = panel_url

    # cleanup refboard for tidiness
    if ref_board and ref_board.exists():
        try:
            ref_board.unlink()
        except Exception:
            pass

    # Persist panels.json for possible debugging
    (out_dir / "node.json").write_text(
        json.dumps(
            {
                "node_id": node_id,
                "summary": summary,
                "narration": narration,
                "dialogue": dialogue,
                "storyboard_panels": panels,
                "ops": [op.model_dump() for op in req.ops],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    storyboard_lines = _build_storyboard_lines(panels, narration)
    log.info("[interact] total %.1fs — done, node_id=%s", time.time() - t0, node_id)

    return {
        "node_id": node_id,
        "type": "narrative",
        "summary": summary,
        "narration": narration,
        "dialogue": [
            {
                "speaker": d.get("speaker", ""),
                "content": d.get("content", ""),
                "tone": d.get("tone", ""),
            }
            for d in (dialogue if isinstance(dialogue, list) else [])
        ],
        "storyboard": storyboard_lines,
        "comic_url": panel_url,
        "thumbnail_url": thumb_url,
    }
