import sys
from pathlib import Path

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
from ..models import InteractRequest, InteractResponse
from ..scene_loader import scene_payload

# reuse existing project code
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.image_generation.seedream_client import generate_image_bytes  # noqa: E402
from scripts.workflow.story_asset_workflow import create_reference_board  # noqa: E402


def _collect_reference_paths(req: InteractRequest) -> list[Path]:
    paths: list[Path] = [path_for(req.scene_idx, "background")]
    seen = {paths[0]}
    for pl in req.placements:
        try:
            p = resolve_interactive_asset(req.scene_idx, pl.name, pl.kind)
        except FileNotFoundError:
            continue
        if p not in seen:
            paths.append(p)
            seen.add(p)
    for op in req.ops:
        for name, kind in ((op.subject, op.subject_kind), (op.target, op.target_kind)):
            p = resolve_interactive_asset(req.scene_idx, name, kind)
            if p not in seen:
                paths.append(p)
                seen.add(p)
    return paths


def _build_prompt(req: InteractRequest, characters_list: list[str]) -> str:
    scene = scene_payload(req.scene_idx)
    goal = scene.get("interaction_goal", "") if scene.get("type") == "interactive" else ""
    op_lines = [
        f"{i + 1}. 「{op.subject}」对「{op.target}」：{op.action}"
        for i, op in enumerate(req.ops)
    ]
    chars_str = "、".join(characters_list) if characters_list else "当前角色"
    return (
        "这是一个为学龄前儿童设计的互动故事场景。"
        "请根据以下信息生成一张温暖、色彩柔和、手绘绘本风格的插画。\n\n"
        "【场景背景】参考图第一格是场景背景，请在此背景中完成下面的动作。\n"
        f"【互动目标】{goal}\n"
        f"【已出现的角色】{chars_str}，请保持他们的造型一致。\n"
        "【要发生的动作序列】\n"
        + "\n".join(op_lines)
        + "\n\n【画面要求】\n"
        "- 保持与参考图完全一致的角色造型、服装颜色、物品外观\n"
        "- 最终画面展现所有动作依次完成后的结果\n"
        "- 儿童绘本插画风格，暖色调，柔和光线，无文字，无水印\n"
        "- 构图完整，主体清晰，适合 5 岁儿童观看"
    )


def run_interaction(req: InteractRequest) -> InteractResponse:
    session_dir = OUTPUTS_ROOT / req.session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    ref_paths = _collect_reference_paths(req)
    board_path = session_dir / f"{req.scene_idx}_refboard.png"
    create_reference_board(ref_paths, board_path, cell_size=768)

    characters = [p.name for p in req.placements if p.kind == "character"]
    prompt = _build_prompt(req, characters)

    try:
        img_bytes = generate_image_bytes(
            api_key=ARK_API_KEY,
            prompt=prompt,
            size=SEEDREAM_SIZE,
            model=SEEDREAM_MODEL,
            provider=SEEDREAM_PROVIDER,
            reference_images=[board_path],
            timeout=SEEDREAM_TIMEOUT,
        )
    except Exception as e:
        msg = str(e)
        if "timeout" in msg.lower() or "timed out" in msg.lower():
            raise TimeoutError(f"图像生成超时（>{SEEDREAM_TIMEOUT}s）：{msg}") from e
        raise RuntimeError(msg) from e

    out_path = session_dir / f"{req.scene_idx}_result.png"
    out_path.write_bytes(img_bytes)
    return InteractResponse(
        result_url=f"/outputs/{req.session_id}/{out_path.name}",
        prompt_used=prompt,
    )
