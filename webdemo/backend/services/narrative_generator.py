import io
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

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
) -> str:
    op_lines = "\n".join(_format_ops(ops)) or "（没有具体操作，只是场景的自然发展）"
    custom_str = (
        "、".join(p.name for p in custom_props) or "（无）"
    )
    return (
        "你是一位儿童绘本的故事编剧，正在根据孩子的互动实时扩展故事。\n"
        "请生成一个新的叙事场景，内容要紧贴孩子安排的互动，风格温暖友善，适合 5 岁儿童。\n\n"
        f"【整本故事大纲】{story_summary}\n"
        f"【上一幕交互目标】{scene.get('interaction_goal', '')}\n"
        f"【上一幕初始画面】{scene.get('initial_frame', '')}\n"
        f"【已出现的角色】{'、'.join(active_characters) or '（无）'}\n"
        f"【已出现的物品】{'、'.join(active_objects) or '（无）'}\n"
        f"【小朋友新创造的物品】{custom_str}\n\n"
        f"【小朋友安排的互动序列】\n{op_lines}\n\n"
        "请严格输出 JSON（不要包含任何解释或代码块标记），结构如下：\n"
        "{\n"
        '  "summary": "1 句话总结这一幕发生了什么（30 字内）",\n'
        '  "narration": "2-3 句旁白（100 字内），口语化、有画面感",\n'
        '  "dialogue": [{"speaker":"角色名","content":"对话","tone":"语气"}],  // 1-4 条，可以为空数组\n'
        '  "storyboard_panels": [\n'
        '    {"panel":1, "description":"左上画面描述，明确谁在哪里做什么，以及表情姿态"},\n'
        '    {"panel":2, "description":"右上画面描述"},\n'
        '    {"panel":3, "description":"左下画面描述"},\n'
        '    {"panel":4, "description":"右下画面描述"}\n'
        "  ]\n"
        "}\n"
        "要求：\n"
        "- 四个画面是同一幕内部的连续推进：起始、发展、转折、结果\n"
        "- 紧贴孩子安排的互动，让孩子的选择真正改变故事\n"
        "- 不要生硬地返回到原作剧情，也不要出现危险/负面内容"
    )


def _collect_reference_paths(
    req: InteractRequest,
    scene_chars: list[str],
) -> list[Path]:
    """Background + global character PNGs + objects used in ops + custom_props."""
    paths: list[Path] = []
    seen: set[Path] = set()

    # background
    bg = path_for(req.scene_idx, "background")
    if bg.exists():
        paths.append(bg)
        seen.add(bg)

    # global characters (full body, transparent) for all active scene chars
    for name in scene_chars:
        gc = path_for(req.scene_idx, "global_character", name)
        if gc.exists() and gc not in seen:
            paths.append(gc)
            seen.add(gc)

    # objects appearing in ops
    for op in req.ops:
        for n, k in ((op.subject, op.subject_kind), (op.target, op.target_kind)):
            if not n or not k:
                continue
            try:
                p = resolve_interactive_asset(req.scene_idx, n, k)
                if p not in seen:
                    paths.append(p)
                    seen.add(p)
            except FileNotFoundError:
                continue

    # custom props (user-generated, absolute path under outputs)
    for cp in req.custom_props:
        rel = cp.url.lstrip("/")
        candidate = (PROJECT_ROOT / "webdemo" / rel).resolve()
        if candidate.exists() and candidate not in seen:
            paths.append(candidate)
            seen.add(candidate)

    return paths


def _storyboard_from_panels(panels: list[dict[str, Any]]) -> str:
    head = "根据当前的 event summary 设计一组漫画，整体风格为彩铅手绘风格，童趣可爱，按照田字格分隔四格漫画分镜构图，适用于儿童绘本。"
    labels = ["画面一（左上）", "画面二（右上）", "画面三（左下）", "画面四（右下）"]
    lines = [head]
    for idx, label in enumerate(labels):
        panel = panels[idx] if idx < len(panels) else {}
        desc = str(panel.get("description", "")).strip()
        lines.append(f"{label}：")
        lines.append(f"画面描述：{desc}")
    return "\n".join(lines)


def _build_storyboard_lines(narration: str, dialogue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    if narration.strip():
        lines.append({"speaker": "旁白", "text": narration.strip(), "kind": "narration", "tone": ""})
    for d in dialogue or []:
        content = str(d.get("content", "")).strip()
        if not content:
            continue
        lines.append(
            {
                "speaker": str(d.get("speaker", "")).strip() or "角色",
                "text": content,
                "kind": "dialogue",
                "tone": str(d.get("tone", "")),
            }
        )
    return lines


def _write_thumb(src: Path, dst: Path) -> None:
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((THUMB_SIZE, THUMB_SIZE))
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst, format="JPEG", quality=85)


def generate_dynamic_node(req: InteractRequest) -> dict[str, Any]:
    scene = _load_scene_json(req.scene_idx)
    story = load_story()
    story_summary = story.get("story_summary", "")

    scene_char_names = [c["name"] for c in scene.get("characters", [])]
    scene_obj_names = [o["name"] for o in scene.get("objects", [])]

    # 1) Qwen: narrative content
    qwen_prompt = _build_qwen_prompt(
        scene=scene,
        story_summary=story_summary,
        ops=req.ops,
        active_characters=scene_char_names,
        active_objects=scene_obj_names,
        custom_props=req.custom_props,
    )
    try:
        result = call_json(qwen_prompt, temperature=0.6, timeout=45)
    except QwenError as e:
        raise RuntimeError(f"故事文本生成失败：{e}") from e

    summary = str(result.get("summary", "")).strip() or "小朋友继续推进了故事。"
    narration = str(result.get("narration", "")).strip() or summary
    dialogue = result.get("dialogue") or []
    panels = result.get("storyboard_panels") or []

    # 2) Seedream: 4-panel comic
    storyboard_text = _storyboard_from_panels(panels)
    ref_paths = _collect_reference_paths(req, scene_char_names)

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
        "objects": [
            {"name": cp.name, "appearance_description": f"小朋友创作的「{cp.name}」"}
            for cp in req.custom_props
        ]
        + scene.get("objects", []),
        "dialogue": dialogue if isinstance(dialogue, list) else [],
    }
    seed_prompt = build_narrative_comic_prompt(pseudo_scene, storyboard_text)

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
        raise RuntimeError(f"四格漫画生成失败：{e}") from e

    panel_path = out_dir / "panel.png"
    panel_path.write_bytes(img_bytes)
    thumb_path = out_dir / "thumb.jpg"
    _write_thumb(panel_path, thumb_path)

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

    storyboard_lines = _build_storyboard_lines(narration, dialogue)

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
        "comic_url": f"/outputs/{req.session_id}/dynamic/{node_id}/panel.png",
        "thumbnail_url": f"/outputs/{req.session_id}/dynamic/{node_id}/thumb.jpg",
    }
