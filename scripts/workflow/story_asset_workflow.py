import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import json
import math
import os
import re
import shutil
import sys
from threading import Lock
from pathlib import Path
from typing import Any, Iterable

import requests

CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image
from tqdm import tqdm

from scripts.image_generation.seedream_client import DEFAULT_MODEL as DEFAULT_SEEDREAM_MODEL
from scripts.image_generation.seedream_client import build_grid_prompt
from scripts.image_generation.seedream_client import generate_image_to_path
from scripts.image_processing.postprocess_grid import export_cells, postprocess_single_asset, remove_background_dispatch
from scripts.story.story_scene_splitter import (
    DEFAULT_BASE_URL,
    INTERACTIVE_SCENE,
    NARRATIVE_SCENE,
    call_bailian_chat,
    is_interactive_scene,
    is_narrative_scene,
    load_story_text,
    normalize_name,
)

DEFAULT_QWEN_MODEL = "qwen3.6-flash-2026-04-16"
PLACEMENT_VISION_MODEL = "qwen3.6-flash-2026-04-16"
MIN_SEEDREAM_PIXELS = 3686400
DEFAULT_MAX_WORKERS = min(8, max(4, (os.cpu_count() or 4)))
PROGRESS_LOCK = Lock()


def _encode_image_b64_resized(path: Path, max_size: int = 768) -> str:
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    if max(w, h) > max_size:
        scale = max_size / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def request_vision_json(
    api_key: str,
    model: str,
    images: list[tuple[str, str]],
    text_prompt: str,
    base_url: str,
    timeout: int,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    content: list[dict] = [
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        for mime, b64 in images
    ]
    content.append({"type": "text", "text": text_prompt})
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.3,
        "stream": False,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Vision API HTTP {resp.status_code}: {resp.text[:400]}")
    raw = resp.json()["choices"][0]["message"]["content"]
    if isinstance(raw, str):
        m = re.search(r"\{[\s\S]*\}", raw)
        return json.loads(m.group(0) if m else raw)
    return raw


def _fallback_placements(scene: dict[str, Any]) -> list[dict[str, Any]]:
    chars = scene.get("characters", []) or []
    objs = scene.get("objects", []) or []
    result = []
    if chars:
        xs = [0.5] if len(chars) == 1 else [0.2 + 0.6 * i / (len(chars) - 1) for i in range(len(chars))]
        for c, x in zip(chars, xs):
            result.append({"name": c["name"], "kind": "character", "x": x, "y": 0.72, "scale": 1.0, "rotation": 0.0})
    for i, o in enumerate(objs):
        row, col = divmod(i, 3)
        result.append({"name": o["name"], "kind": "object", "x": 0.2 + 0.3 * col, "y": 0.25 + 0.18 * row, "scale": 0.9, "rotation": 0.0})
    return result


def precompute_scene_placements(
    scene: dict[str, Any],
    scene_root: Path,
    dashscope_api_key: str,
    base_url: str,
    timeout: int,
) -> None:
    images: list[tuple[str, str]] = []
    bg_png = scene_root / "background" / "background.png"
    if bg_png.exists():
        images.append(("image/png", _encode_image_b64_resized(bg_png, max_size=768)))
    for character in scene.get("characters", []):
        stem = safe_stem(character["name"])
        char_png = scene_root / "image" / "characters" / f"{stem}_transparent.png"
        if not char_png.exists():
            char_png = scene_root / "image" / "characters" / f"{stem}.png"
        if char_png.exists():
            images.append(("image/png", _encode_image_b64_resized(char_png, max_size=512)))

    scene_info = {
        "interaction_goal": scene.get("interaction_goal", ""),
        "initial_frame": scene.get("initial_frame", ""),
        "background": scene.get("background_visual_description", ""),
        "characters": [{"name": c["name"], "pose": c.get("pose", "")} for c in scene.get("characters", [])],
        "objects": [{"name": o["name"], "description": o.get("appearance_description", "")} for o in scene.get("objects", [])],
    }
    prompt = (
        "你是儿童互动故事书的美术布局师。图片依次是：背景图、各角色参考图。\n"
        "请根据图像内容和场景描述，为每个角色与物品规划合理的起始位置。\n\n"
        "坐标系：x 从 0（最左）到 1（最右）；y 从 0（最上）到 1（最下）。\n"
        "规则：\n"
        "- 角色通常站在画面下半部分 (y 在 0.55-0.85)，不要重叠。\n"
        "- 大型物品（如树、床）放在背景中后景，可稍靠上 (y 在 0.35-0.60)。\n"
        "- 小道具（如鲜花、蘑菇、蝴蝶）分散在前景和中景，避免堆叠。\n"
        "- 任何 x、y 都要在 0.05-0.95 之间，不能超出画面。\n"
        "- 飞行/悬浮类物品（蝴蝶、鸟巢）y 可以较小。\n\n"
        '输出严格 JSON：{"placements":[{"name":"名字","kind":"character"或"object","x":0.xx,"y":0.xx,"scale":0.6-1.3,"rotation":-15到15}]}\n'
        "不要输出任何其他文字。\n\n"
        f"场景信息：\n{json.dumps(scene_info, ensure_ascii=False, indent=2)}"
    )

    valid_names = {c["name"] for c in scene.get("characters", [])} | {o["name"] for o in scene.get("objects", [])}
    raw_placements: list[dict] = []
    if images:
        try:
            result = request_vision_json(
                api_key=dashscope_api_key,
                model=PLACEMENT_VISION_MODEL,
                images=images,
                text_prompt=prompt,
                base_url=base_url,
                timeout=timeout,
            )
            raw_placements = result.get("placements") or []
        except Exception as e:
            print(f"[placements] vision model failed for scene {scene.get('scene_index')}: {e}")

    placements: list[dict] = []
    seen: set[str] = set()
    for item in raw_placements:
        name = item.get("name")
        if name not in valid_names:
            continue
        kind = item.get("kind")
        if kind not in ("character", "object"):
            kind = "character" if any(c["name"] == name for c in scene.get("characters", [])) else "object"
        placements.append({
            "name": name,
            "kind": kind,
            "x": max(0.02, min(0.98, float(item.get("x", 0.5)))),
            "y": max(0.02, min(0.98, float(item.get("y", 0.5)))),
            "scale": max(0.4, min(1.5, float(item.get("scale", 1.0)))),
            "rotation": max(-30.0, min(30.0, float(item.get("rotation", 0.0)))),
        })
        seen.add(name)
    for fb in _fallback_placements(scene):
        if fb["name"] not in seen:
            placements.append(fb)

    save_json(scene_root / "placements.json", {"placements": placements})


def update_progress(progress: tqdm | None, message: str, steps: int = 1) -> None:
    if progress is None:
        return
    with PROGRESS_LOCK:
        progress.set_postfix_str(message)
        progress.update(steps)


def safe_stem(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name.strip())
    cleaned = cleaned.strip("_")
    return cleaned or "asset"


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).resolve().read_text(encoding="utf-8"))


def parse_image_size(size: str) -> tuple[int, int]:
    try:
        width_text, height_text = size.lower().split("x", 1)
        width = int(width_text)
        height = int(height_text)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid image size format: {size}. Expected WIDTHxHEIGHT.") from exc
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid image size: {size}. Width and height must be positive.")
    return width, height


def validate_seedream_size(size: str, label: str) -> None:
    width, height = parse_image_size(size)
    pixels = width * height
    if pixels < MIN_SEEDREAM_PIXELS:
        raise ValueError(
            f"{label} size {size} is too small for Seedream. "
            f"It must be at least {MIN_SEEDREAM_PIXELS} pixels in total."
        )


def create_reference_board(image_paths: list[Path], output_path: Path, cell_size: int = 768) -> Path:
    valid_paths = [path for path in image_paths if path.exists()]
    if not valid_paths:
        raise ValueError("At least one reference image is required to build a reference board.")

    cols = min(3, len(valid_paths))
    rows = (len(valid_paths) + cols - 1) // cols
    canvas = Image.new("RGBA", (cols * cell_size, rows * cell_size), (255, 255, 255, 255))

    for index, path in enumerate(valid_paths):
        with Image.open(path) as source:
            image = source.convert("RGBA")
        image.thumbnail((cell_size - 64, cell_size - 64))
        col = index % cols
        row = index // cols
        offset_x = col * cell_size + (cell_size - image.width) // 2
        offset_y = row * cell_size + (cell_size - image.height) // 2
        canvas.alpha_composite(image, (offset_x, offset_y))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return output_path


def chunked(items: list[Any], chunk_size: int) -> list[list[Any]]:
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def pad_grid_entries(entries: list[dict[str, Any]], filler_prefix: str = "__empty_slot__") -> tuple[list[dict[str, Any]], int]:
    padded = list(entries)
    actual_count = len(entries)
    while len(padded) < 9:
        padded.append(
            {
                "name": f"{filler_prefix}{len(padded) + 1}",
                "appearance_description": "",
                "is_placeholder": True,
            }
        )
    return padded, actual_count


def build_partial_asset_grid_prompt(
    entries: list[dict[str, Any]],
    style: str = "colored pencil hand-drawn illustration",
    extra_prompt: str = "",
) -> str:
    if len(entries) == 9 and not any(entry.get("is_placeholder") or entry.get("grid_prompt") for entry in entries) and not extra_prompt.strip():
        return build_grid_prompt(
            objects=[entry["name"] for entry in entries],
            style=style,
            extra_prompt=extra_prompt,
        )

    prompt_parts = [
        "Create one single image arranged as a 3x3 equal-sized grid.",
        "Pure white background.",
        "All nine cells must be exactly the same size and aligned cleanly.",
        "Use a consistent hand-drawn illustration style across all non-empty cells.",
        "No visible grid lines, no text, no labels.",
    ]
    for index, entry in enumerate(entries, start=1):
        if entry.get("is_placeholder"):
            prompt_parts.append(f"Cell {index}: keep this cell completely blank, pure white, with no object at all.")
        else:
            cell_prompt = entry.get("grid_prompt", "").strip()
            description = entry.get("appearance_description", "").strip()
            if cell_prompt:
                prompt_parts.append(f"Cell {index}: {cell_prompt}")
            else:
                if description:
                    prompt_parts.append(f"Cell {index}: {entry['name']}. Appearance: {description}.")
                else:
                    prompt_parts.append(f"Cell {index}: {entry['name']}.")
    if extra_prompt.strip():
        prompt_parts.append(extra_prompt.strip())
    prompt_parts.append(f"Overall style keyword: {style}.")
    return " ".join(prompt_parts)


def generate_object_grid_assets(
    api_key: str,
    provider: str,
    model: str,
    size: str,
    entries: list[dict[str, Any]],
    output_dir: Path,
    work_dir: Path,
    batch_prefix: str,
    overall_progress: tqdm | None = None,
    overall_label: str | None = None,
    parallel_workers: int = 1,
) -> list[dict[str, str | int]]:
    batches = chunked(entries, 9)
    batch_progress = tqdm(total=len(batches), desc=f"{batch_prefix} object grids", unit="grid", disable=len(batches) <= 1)
    results: list[tuple[int, list[dict[str, str | int]]]] = []

    def run_batch(batch_index: int, batch: list[dict[str, Any]]) -> tuple[int, list[dict[str, str | int]]]:
        batch_results: list[dict[str, str | int]] = []
        padded_entries, actual_count = pad_grid_entries(batch)
        batch_stem = f"{batch_prefix}_{batch_index:02d}"
        raw_grid_path = work_dir / f"{batch_stem}_raw.png"
        transparent_grid_path = work_dir / f"{batch_stem}_transparent.png"
        extraction_dir = work_dir / f"{batch_stem}_extracted"

        generate_image_to_path(
            api_key=api_key,
            prompt=build_partial_asset_grid_prompt(padded_entries),
            size=size,
            output_path=raw_grid_path,
            model=model,
            provider=provider,
        )

        with Image.open(raw_grid_path) as raw_grid_image:
            transparent = remove_background_dispatch(
                image=raw_grid_image,
                method="rembg",
                rembg_model="u2net",
                rembg_alpha_matting=True,
                white_tolerance=42,
                white_min_channel=235,
                soften_edge=18,
                show_progress=False,
            )
        transparent.save(transparent_grid_path)

        manifest = export_cells(
            transparent,
            output_dir=extraction_dir,
            object_names=[entry["name"] for entry in padded_entries],
            alpha_threshold=8,
            crop_padding=12,
            outline_width=10,
            outline_blur=1,
            svg_colormode="color",
            svg_hierarchical="stacked",
            svg_mode="spline",
            show_progress=False,
        )

        for item_index, item in enumerate(manifest, start=1):
            source_png = Path(str(item["png"]))
            source_svg = Path(str(item["svg"]))
            entry = padded_entries[item_index - 1]
            if item_index > actual_count or entry.get("is_placeholder"):
                if source_png.exists():
                    source_png.unlink()
                if source_svg.exists():
                    source_svg.unlink()
                continue

            stem = safe_stem(entry["name"])
            target_png = output_dir / f"{stem}.png"
            target_svg = output_dir / f"{stem}.svg"
            target_png.parent.mkdir(parents=True, exist_ok=True)
            target_svg.parent.mkdir(parents=True, exist_ok=True)
            source_png.replace(target_png)
            source_svg.replace(target_svg)
            batch_results.append(
                {
                    "name": entry["name"],
                    "png": str(target_png.resolve()),
                    "svg": str(target_svg.resolve()),
                    "width": item["width"],
                    "height": item["height"],
                }
            )
        return batch_index, batch_results

    if parallel_workers > 1 and len(batches) > 1:
        with ThreadPoolExecutor(max_workers=min(parallel_workers, len(batches))) as executor:
            future_map = {
                executor.submit(run_batch, batch_index, batch): batch_index
                for batch_index, batch in enumerate(batches, start=1)
            }
            for future in as_completed(future_map):
                batch_index, batch_results = future.result()
                results.append((batch_index, batch_results))
                batch_progress.update(1)
                update_progress(overall_progress, overall_label or f"{batch_prefix} object grid {batch_index}")
    else:
        for batch_index, batch in enumerate(batches, start=1):
            batch_index, batch_results = run_batch(batch_index, batch)
            results.append((batch_index, batch_results))
            batch_progress.update(1)
            update_progress(overall_progress, overall_label or f"{batch_prefix} object grid {batch_index}")

    batch_progress.close()
    flattened: list[dict[str, str | int]] = []
    for _, batch_results in sorted(results, key=lambda item: item[0]):
        flattened.extend(batch_results)
    return flattened


def prepare_global_character_grid_entries(characters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for character in characters:
        name = character["name"]
        appearance = character["appearance_description"]
        entries.append(
            {
                "name": name,
                "appearance_description": appearance,
                "grid_prompt": (
                    f"{name}. Full-body character only, head-to-toe fully visible inside the cell. "
                    f"Appearance: {appearance}. "
                    "One complete standing character silhouette, centered, pure white background, no extra props, no other people."
                ),
            }
        )
    return entries


def prepare_scene_object_grid_entries(scene: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    initial_frame = scene.get("initial_frame", "").strip()
    background = scene.get("background_visual_description", "").strip()

    for obj in scene.get("objects", []):
        name = obj["name"]
        appearance = obj["appearance_description"]
        grid_prompt = (
            f"{name}. Appearance: {appearance}. "
            f"This prop must naturally belong to the same environment described as: {background}. "
        )
        if initial_frame:
            grid_prompt += f"Opening frame reference for scale and scene fit: {initial_frame}. "
        grid_prompt += (
            "Render it as a believable prop from that exact scene world. "
            "Keep only the object itself on a pure white background. "
            "No people, no animals, no extra props, no ground plane, no environment fragments."
        )
        entries.append(
            {
                "name": name,
                "appearance_description": appearance,
                "grid_prompt": grid_prompt,
            }
        )
    return entries


def generate_isolated_asset(
    api_key: str,
    provider: str,
    model: str,
    size: str,
    prompt: str,
    raw_output_path: Path,
    png_output_path: Path,
    svg_output_path: Path,
    transparent_output_path: Path,
    reference_images: list[Path] | None = None,
) -> dict[str, str | int]:
    generate_image_to_path(
        api_key=api_key,
        prompt=prompt,
        size=size,
        output_path=raw_output_path,
        model=model,
        provider=provider,
        reference_images=[str(path) for path in reference_images or []],
    )
    return postprocess_single_asset(
        input_path=raw_output_path,
        png_output_path=png_output_path,
        svg_output_path=svg_output_path,
        transparent_output_path=transparent_output_path,
    )


def build_global_character_prompt(character: dict[str, Any]) -> str:
    name = character["name"]
    appearance = character["appearance_description"]
    return (
        f"Generate a single full-body character concept image of {name}. "
        f"Appearance: {appearance}. "
        "Show the entire body from head to toe. "
        "Single character only, no other people, no extra props unless they are part of the character's essential design. "
        "Centered composition, white background, colored pencil hand-drawn illustration style, clean silhouette, consistent proportions."
    )


def build_global_object_prompt(obj: dict[str, Any]) -> str:
    return (
        f"Generate a single isolated object concept image of {obj['name']}. "
        f"Appearance: {obj['appearance_description']}. "
        "Single object only, centered composition, white background, colored pencil hand-drawn illustration style, no extra objects, no text."
    )


def build_scene_character_prompt(scene: dict[str, Any], character: dict[str, Any], related_objects: list[dict[str, Any]]) -> str:
    related_note = ""
    if related_objects:
        names = ", ".join(item["name"] for item in related_objects)
        relation_text = " ".join(item.get("relationship", "").strip() for item in related_objects if item.get("relationship"))
        related_note = (
            f"Include only these bound scene objects with the character when needed: {names}. "
            f"Relationship notes: {relation_text}. "
        )
    return (
        f"Generate a single character image for the scene. Character: {character['name']}. "
        f"Pose: {character['pose']}. "
        "Use the provided character reference image to preserve identity consistency. "
        "If bound object reference images are also provided, use them only for the character-object combination in this foreground asset. "
        f"{related_note}"
        "Do not include background scene information, environment details, or any unrelated props. "
        "No other people, no text. "
        "White background, colored pencil hand-drawn illustration style, clean cutout-friendly silhouette."
    )


def build_scene_object_prompt(scene: dict[str, Any], obj: dict[str, Any]) -> str:
    return (
        f"Generate a single isolated prop image for the scene. Object: {obj['name']}. "
        f"Appearance: {obj['appearance_description']}. "
        f"Scene context: {scene.get('initial_frame', scene['event_summary'])}. "
        f"Background environment: {scene['background_visual_description']}. "
        "The prop must feel like it truly belongs inside that environment and matches that world's materials and scale. "
        "Single object only, white background, colored pencil hand-drawn illustration style, no people, no text."
    )


def build_background_prompt(scene: dict[str, Any]) -> str:
    scene_type = scene["scene_type"]
    summary = scene["event_summary"]
    initial_frame = scene.get("initial_frame", "")
    return (
        "Generate a clean story background environment only. "
        f"Scene type: {scene_type}. "
        f"Scene summary: {summary}. "
        f"Opening frame reference: {initial_frame}. "
        f"Background description: {scene['background_visual_description']}. "
        "Do not include any characters, no standalone props, no text, no speech bubbles. "
        "Keep the composition suitable for later placing foreground characters and props with believable scale. "
        "Use a consistent colored pencil hand-drawn illustration style."
    )


def build_global_assets(
    story_payload: dict[str, Any],
    output_root: Path,
    api_key: str,
    provider: str,
    seedream_model: str,
    asset_size: str,
    overall_progress: tqdm | None = None,
    show_progress: bool = True,
    scene_asset_workers: int = 1,
) -> dict[str, dict[str, str]]:
    global_dir = output_root / "global"
    raw_dir = global_dir / "_raw"
    character_work_dir = global_dir / "_character_grids"
    character_dir = global_dir / "characters"
    object_dir = global_dir / "objects"
    object_work_dir = global_dir / "_object_grids"
    transparent_dir = global_dir / "_transparent"
    manifests = {"characters": {}, "objects": {}}

    global_content = story_payload.get("global_content", {})
    characters = list(global_content.get("characters", []))
    objects = list(global_content.get("objects", []))
    total = (math.ceil(len(characters) / 9) if characters else 0) + (math.ceil(len(objects) / 9) if objects else 0)
    progress = tqdm(total=total, desc="Generating global assets", unit="asset", disable=not show_progress)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures: dict[Any, str] = {}

        if characters:
            futures[executor.submit(
                generate_object_grid_assets,
                api_key=api_key,
                provider=provider,
                model=seedream_model,
                size=asset_size,
                entries=prepare_global_character_grid_entries(characters),
                output_dir=character_dir,
                work_dir=character_work_dir,
                batch_prefix="global_characters",
                overall_progress=overall_progress,
                overall_label="global characters grid",
                parallel_workers=scene_asset_workers,
            )] = "characters"

        if objects:
            futures[executor.submit(
                generate_object_grid_assets,
                api_key=api_key,
                provider=provider,
                model=seedream_model,
                size=asset_size,
                entries=objects,
                output_dir=object_dir,
                work_dir=object_work_dir,
                batch_prefix="global_objects",
                overall_progress=overall_progress,
                overall_label="global objects grid",
                parallel_workers=scene_asset_workers,
            )] = "objects"

        for future in as_completed(futures):
            kind = futures[future]
            results = future.result()
            for result in results:
                manifests[kind][normalize_name(str(result["name"]))] = {
                    "name": str(result["name"]),
                    "png": str(result["png"]),
                    "svg": str(result["svg"]),
                }
            if kind == "characters":
                progress.update(math.ceil(len(characters) / 9))
            else:
                progress.update(math.ceil(len(objects) / 9))

    progress.close()
    save_json(global_dir / "manifest.json", manifests)
    return manifests


def load_existing_global_manifest(output_root: Path) -> dict[str, dict[str, dict[str, str]]]:
    manifest_path = output_root / "global" / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Global manifest not found: {manifest_path}")
    data = load_json(manifest_path)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid global manifest: {manifest_path}")
    return data


def ensure_interactive_scene_directories(scene_root: Path) -> None:
    (scene_root / "image" / "characters").mkdir(parents=True, exist_ok=True)
    (scene_root / "image" / "objects").mkdir(parents=True, exist_ok=True)
    (scene_root / "background").mkdir(parents=True, exist_ok=True)
    (scene_root / "comic").mkdir(parents=True, exist_ok=True)


def ensure_narrative_scene_directories(scene_root: Path) -> None:
    scene_root.mkdir(parents=True, exist_ok=True)
    (scene_root / "comic").mkdir(parents=True, exist_ok=True)


def cleanup_narrative_scene_artifacts(scene_root: Path) -> None:
    for name in ("image", "background", "_refs", "_object_grids"):
        target = scene_root / name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)


def request_text_completion(
    api_key: str,
    model: str,
    prompt: str,
    base_url: str,
    timeout: int,
) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "stream": False,
        "enable_thinking": False,
    }
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Storyboard request failed with HTTP {response.status_code} at {url}\n"
            f"Response body:\n{response.text[:3000]}"
        )
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part.strip() for part in parts if part and part.strip()).strip()
    return str(content).strip()


def build_narrative_storyboard_prompt(scene: dict[str, Any]) -> str:
    scene_payload = {
        "scene_index": scene.get("scene_index"),
        "scene_type": scene.get("scene_type"),
        "event_summary": scene.get("event_summary"),
        "narration": scene.get("narration"),
        "dialogue": scene.get("dialogue", []),
        "characters": scene.get("characters", []),
        "objects": scene.get("objects", []),
        "background_visual_description": scene.get("background_visual_description"),
    }
    return f"""
请根据当前 scene.json 的内容，先构造一份适合儿童绘本的四格漫画分镜。

要求：
1. 整体风格为彩铅手绘风格，童趣可爱，四格漫画分镜构图，适用于儿童绘本。
2. 必须严格输出以下结构，不要输出 JSON，不要输出解释：
根据当前的event summary设计一组漫画，整体风格为彩铅手绘风格，童趣可爱，按照田字格分隔四格漫画分镜构图，适用于儿童绘本。
画面一（左上）：
画面描述：
画面二（右上）：
画面描述：
画面三（左下）：
画面描述：
画面四（右下）：
画面描述：
3. 四个画面必须是同一个叙事场景内部的连续推进，分别体现起始、发展、过渡、结果。
4. 你可以使用 scene 中的 narration、dialogue、event_summary 来帮助拆分四格，但不要照抄成图片中的文字。
5. 需要综合 background_visual_description，以及 scene 中出现的人物和物体来做分镜安排。
6. 这是分镜构造稿，不是最终图片提示词，所以可以写清楚每格里谁在做什么、整体场面如何推进。

scene.json 内容：
{json.dumps(scene_payload, ensure_ascii=False, indent=2)}
""".strip()


def build_narrative_comic_prompt(scene: dict[str, Any], storyboard_text: str) -> str:
    character_lines: list[str] = []
    for character in scene.get("characters", []):
        related = character.get("related_objects", [])
        related_note = ""
        if isinstance(related, list) and related:
            names = ", ".join(item.get("name", "") for item in related if isinstance(item, dict) and item.get("name"))
            if names:
                related_note = f" Related props to keep consistent: {names}."
        character_lines.append(f"{character['name']}.{related_note}")

    dialogue_lines: list[str] = []
    for line in scene.get("dialogue", []):
        if not isinstance(line, dict):
            continue
        speaker = str(line.get("speaker", "")).strip()
        content = str(line.get("content", "")).strip()
        tone = str(line.get("tone", "")).strip()
        if speaker and content and tone:
            dialogue_lines.append(f"{speaker}（{tone}）：“{content}”")

    object_lines: list[str] = []
    for obj in scene.get("objects", []):
        if not isinstance(obj, dict):
            continue
        name = str(obj.get("name", "")).strip()
        description = str(obj.get("appearance_description", "")).strip()
        if name and description:
            object_lines.append(f"{name}: {description}")

    prompt_parts = [
        "Generate one single children's story comic page arranged as four continuous comic panels in one image.",
        "The image must contain exactly 4 connected narrative panels that read in order from panel 1 to panel 4.",
        "Colored pencil hand-drawn illustration style.",
        "This is a narrative scene, so create a complete four-beat story progression instead of isolated assets.",
        f"Scene summary: {scene['event_summary']}.",
        f"Narration caption: {scene.get('narration', '')}.",
        f"Background environment: {scene['background_visual_description']}.",
        f"Storyboard plan to follow: {storyboard_text}",
    ]
    if character_lines:
        prompt_parts.append("Characters to keep consistent with references: " + " ".join(character_lines))
    if object_lines:
        prompt_parts.append("Consistent recurring props in this scene: " + " ".join(object_lines))
    if dialogue_lines:
        prompt_parts.append("Use these dialogue beats only as storytelling guidance for facial expression and staging, not as visible text: " + " ".join(dialogue_lines))
    prompt_parts.append(
        "Break the narrative scene into four small sequential beats that naturally show the beginning, development, transition, and end of the same scene."
    )
    prompt_parts.append(
        "Compose it like a polished storybook comic strip with coherent staging, expressive acting, and consistent proportions across all four panels."
    )
    prompt_parts.append(
        "Keep the visual style soft, colorful, and clearly hand-drawn with colored pencils."
    )
    prompt_parts.append(
        "Do not render any words, captions, dialogue balloons, narration boxes, labels, or sound effects anywhere in the image."
    )
    return " ".join(part for part in prompt_parts if part.strip())


def build_interactive_storyboard_prompt(scene: dict[str, Any]) -> str:
    scene_payload = {
        "scene_index": scene.get("scene_index"),
        "scene_type": scene.get("scene_type"),
        "interaction_goal": scene.get("interaction_goal"),
        "initial_frame": scene.get("initial_frame"),
        "event_outcome": scene.get("event_outcome"),
        "narration": scene.get("narration"),
        "dialogue": scene.get("dialogue", []),
        "characters": scene.get("characters", []),
        "objects": scene.get("objects", []),
        "background_visual_description": scene.get("background_visual_description"),
    }
    return f"""
请基于当前 scene.json 的内容（这是一段交互场景在原故事里的发展过程），构造一份适合儿童绘本的四格漫画分镜。

要求：
1. 整体风格为彩铅手绘风格，童趣可爱，四格漫画分镜构图，适用于儿童绘本。
2. 必须严格输出以下结构，不要输出 JSON，不要输出解释：
根据 initial_frame -> interaction_goal -> event_outcome 推进的发展过程设计一组漫画，整体风格为彩铅手绘风格，童趣可爱，按照田字格分隔四格漫画分镜构图，适用于儿童绘本。
画面一（左上）：
画面描述：
画面二（右上）：
画面描述：
画面三（左下）：
画面描述：
画面四（右下）：
画面描述：
3. 四个画面必须是这一交互场景内部的连续推进：以 initial_frame 为起始，过渡至 interaction_goal 中描述的关键互动，最终以 event_outcome 收尾。
4. 你可以使用 narration、interaction_goal、event_outcome 来帮助拆分四格，但不要照抄成图片中的文字。
5. 需要综合 background_visual_description，以及 scene 中出现的人物和物体来做分镜安排。
6. 这是分镜构造稿，不是最终图片提示词，所以可以写清楚每格里谁在做什么、整体场面如何推进。

scene.json 内容：
{json.dumps(scene_payload, ensure_ascii=False, indent=2)}
""".strip()


def build_interactive_comic_prompt(scene: dict[str, Any], storyboard_text: str) -> str:
    character_lines: list[str] = []
    for character in scene.get("characters", []):
        related = character.get("related_objects", [])
        related_note = ""
        if isinstance(related, list) and related:
            names = ", ".join(item.get("name", "") for item in related if isinstance(item, dict) and item.get("name"))
            if names:
                related_note = f" Related props to keep consistent: {names}."
        character_lines.append(f"{character['name']}.{related_note}")

    object_lines: list[str] = []
    for obj in scene.get("objects", []):
        if not isinstance(obj, dict):
            continue
        name = str(obj.get("name", "")).strip()
        description = str(obj.get("appearance_description", "")).strip()
        if name and description:
            object_lines.append(f"{name}: {description}")

    initial_frame = str(scene.get("initial_frame", "")).strip()
    interaction_goal = str(scene.get("interaction_goal", "")).strip()
    event_outcome = str(scene.get("event_outcome", "")).strip()
    narration = str(scene.get("narration", "")).strip()

    dialogue_lines: list[str] = []
    for line in scene.get("dialogue", []) or []:
        if not isinstance(line, dict):
            continue
        speaker = str(line.get("speaker", "")).strip()
        content = str(line.get("content", "")).strip()
        tone = str(line.get("tone", "")).strip()
        if speaker and content:
            if tone:
                dialogue_lines.append(f"{speaker}（{tone}）：“{content}”")
            else:
                dialogue_lines.append(f"{speaker}：“{content}”")

    prompt_parts = [
        "Generate one single children's story comic page arranged as four continuous comic panels in one image.",
        "The image must contain exactly 4 connected narrative panels that read in order from panel 1 to panel 4.",
        "Colored pencil hand-drawn illustration style.",
        "This depicts the original development arc of an interactive scene from the source story.",
        f"Initial frame (panel 1 baseline): {initial_frame}.",
        f"Interaction goal driving the middle panels: {interaction_goal}.",
        f"Event outcome to land on by panel 4: {event_outcome}.",
        f"Background environment: {scene.get('background_visual_description', '')}.",
        f"Storyboard plan to follow: {storyboard_text}",
    ]
    if narration:
        prompt_parts.append(f"Narration caption (for staging only, do not render): {narration}.")
    if dialogue_lines:
        prompt_parts.append(
            "Use these dialogue beats only as storytelling guidance for facial expression and staging, not as visible text: "
            + " ".join(dialogue_lines)
        )
    if character_lines:
        prompt_parts.append("Characters to keep consistent with references: " + " ".join(character_lines))
    if object_lines:
        prompt_parts.append("Consistent recurring props in this scene: " + " ".join(object_lines))
    prompt_parts.append(
        "Break the arc into four sequential beats: setup (initial_frame), rising action toward the interaction, the climax of the interaction, and the outcome."
    )
    prompt_parts.append(
        "Compose it like a polished storybook comic strip with coherent staging, expressive acting, and consistent proportions across all four panels."
    )
    prompt_parts.append(
        "Keep the visual style soft, colorful, and clearly hand-drawn with colored pencils."
    )
    prompt_parts.append(
        "Do not render any words, captions, dialogue balloons, narration boxes, labels, or sound effects anywhere in the image."
    )
    return " ".join(part for part in prompt_parts if part.strip())


def build_narrative_reference_paths(
    scene: dict[str, Any],
    global_manifest: dict[str, dict[str, dict[str, str]]],
) -> list[Path]:
    reference_paths: list[Path] = []
    seen_paths: set[str] = set()

    for character in scene.get("characters", []):
        if not isinstance(character, dict):
            continue
        global_character = global_manifest["characters"].get(normalize_name(character.get("name", "")))
        if global_character:
            png_path = str(global_character.get("png", "")).strip()
            if png_path and png_path not in seen_paths:
                seen_paths.add(png_path)
                reference_paths.append(Path(png_path))
        for rel in character.get("related_objects", []):
            if not isinstance(rel, dict):
                continue
            global_object = global_manifest["objects"].get(normalize_name(rel.get("name", "")))
            if global_object:
                png_path = str(global_object.get("png", "")).strip()
                if png_path and png_path not in seen_paths:
                    seen_paths.add(png_path)
                    reference_paths.append(Path(png_path))

    for obj in scene.get("objects", []):
        if not isinstance(obj, dict):
            continue
        global_object = global_manifest["objects"].get(normalize_name(obj.get("name", "")))
        if global_object:
            png_path = str(global_object.get("png", "")).strip()
            if png_path and png_path not in seen_paths:
                seen_paths.add(png_path)
                reference_paths.append(Path(png_path))

    return reference_paths


def process_scene(
    scene: dict[str, Any],
    output_root: Path,
    global_manifest: dict[str, dict[str, dict[str, str]]],
    dashscope_api_key: str | None,
    api_key: str,
    provider: str,
    seedream_model: str,
    asset_size: str,
    background_size: str,
    qwen_model: str,
    base_url: str,
    timeout: int,
    overall_progress: tqdm | None = None,
    narrative_only: bool = False,
    scene_asset_workers: int = 1,
) -> None:
    scene_index = int(scene["scene_index"])
    scene_root = output_root / f"{scene_index:03d}"

    if is_narrative_scene(scene["scene_type"]):
        ensure_narrative_scene_directories(scene_root)
        save_json(scene_root / "scene.json", scene)
        update_progress(overall_progress, f"scene {scene_index}: scene.json")

        comic_dir = scene_root / "comic"
        reference_paths = build_narrative_reference_paths(scene, global_manifest)
        ref_board = None
        if reference_paths:
            ref_board = create_reference_board(reference_paths, comic_dir / "_narrative_refs.png")

        comic_raw = comic_dir / "panel_raw.png"
        comic_png = comic_dir / "panel.png"
        storyboard_txt = comic_dir / "storyboard.txt"
        if not dashscope_api_key:
            raise ValueError("Narrative comic generation requires DashScope API key for storyboard construction.")
        storyboard_text = request_text_completion(
            api_key=dashscope_api_key,
            model=qwen_model,
            prompt=build_narrative_storyboard_prompt(scene),
            base_url=base_url,
            timeout=timeout,
        )
        storyboard_txt.write_text(storyboard_text, encoding="utf-8")
        generate_image_to_path(
            api_key=api_key,
            prompt=build_narrative_comic_prompt(scene, storyboard_text),
            size=background_size,
            output_path=comic_raw,
            model=seedream_model,
            provider=provider,
            reference_images=[str(ref_board)] if ref_board else None,
        )
        comic_raw.replace(comic_png)
        save_json(
            scene_root / "manifest.json",
            {
                "comic": str(comic_png.resolve()),
                "storyboard": str(storyboard_txt.resolve()),
                "scene_type": scene["scene_type"],
            },
        )
        if ref_board and ref_board.exists():
            ref_board.unlink()
        if comic_raw.exists():
            comic_raw.unlink(missing_ok=True)
        cleanup_narrative_scene_artifacts(scene_root)
        update_progress(overall_progress, f"scene {scene_index}: narrative comic")
        return

    if narrative_only:
        return

    ensure_interactive_scene_directories(scene_root)
    save_json(scene_root / "scene.json", scene)
    update_progress(overall_progress, f"scene {scene_index}: scene.json")

    background_dir = scene_root / "background"
    background_raw = background_dir / "background_raw.png"
    background_png = background_dir / "background.png"
    image_dir = scene_root / "image"
    ref_dir = scene_root / "_refs"
    ref_dir.mkdir(parents=True, exist_ok=True)
    object_grid_work_dir = scene_root / "_object_grids"

    scene_manifest = {"characters": [], "objects": [], "background": str(background_png)}

    comic_dir = scene_root / "comic"
    comic_raw = comic_dir / "panel_raw.png"
    comic_png = comic_dir / "panel.png"
    storyboard_txt = comic_dir / "storyboard.txt"
    comic_reference_paths = build_narrative_reference_paths(scene, global_manifest)
    comic_ref_board: Path | None = None
    if comic_reference_paths:
        comic_ref_board = create_reference_board(
            comic_reference_paths, comic_dir / "_narrative_refs.png"
        )

    character_jobs: list[tuple[dict[str, Any], Path | None, list[dict[str, Any]]]] = []
    for character in scene.get("characters", []):
        char_name = normalize_name(character["name"])
        global_character = global_manifest["characters"].get(char_name)
        reference_paths: list[Path] = []
        if global_character:
            reference_paths.append(Path(global_character["png"]))

        related_objects: list[dict[str, Any]] = []
        for rel in character.get("related_objects", []):
            rel_name = normalize_name(rel["name"])
            global_object = global_manifest["objects"].get(rel_name)
            if global_object:
                reference_paths.append(Path(global_object["png"]))
                related_objects.append(rel)

        ref_board = None
        if reference_paths:
            ref_board = create_reference_board(reference_paths, ref_dir / f"{safe_stem(character['name'])}_refs.png")
        character_jobs.append((character, ref_board, related_objects))

    def generate_background_task() -> str:
        generate_image_to_path(
            api_key=api_key,
            prompt=build_background_prompt(scene),
            size=background_size,
            output_path=background_raw,
            model=seedream_model,
            provider=provider,
        )
        background_raw.replace(background_png)
        update_progress(overall_progress, f"scene {scene_index}: background")
        return str(background_png)

    def generate_character_task(character: dict[str, Any], ref_board: Path | None, related_objects: list[dict[str, Any]]) -> dict[str, Any]:
        stem = safe_stem(character["name"])
        result = generate_isolated_asset(
            api_key=api_key,
            provider=provider,
            model=seedream_model,
            size=asset_size,
            prompt=build_scene_character_prompt(scene, character, related_objects),
            raw_output_path=image_dir / "characters" / f"{stem}_raw.png",
            png_output_path=image_dir / "characters" / f"{stem}.png",
            svg_output_path=image_dir / "characters" / f"{stem}.svg",
            transparent_output_path=image_dir / "characters" / f"{stem}_transparent.png",
            reference_images=[ref_board] if ref_board else None,
        )
        update_progress(overall_progress, f"scene {scene_index}: character {character['name']}")
        return {"name": character["name"], **result}

    def generate_objects_task() -> list[dict[str, str | int]]:
        return generate_object_grid_assets(
            api_key=api_key,
            provider=provider,
            model=seedream_model,
            size=asset_size,
            entries=prepare_scene_object_grid_entries(scene),
            output_dir=image_dir / "objects",
            work_dir=object_grid_work_dir,
            batch_prefix=f"scene_{scene_index:03d}_objects",
            overall_progress=overall_progress,
            overall_label=f"scene {scene_index}: object grid",
            parallel_workers=scene_asset_workers,
        )

    def generate_interactive_comic_task() -> str | None:
        if not dashscope_api_key:
            return None
        storyboard_text = request_text_completion(
            api_key=dashscope_api_key,
            model=qwen_model,
            prompt=build_interactive_storyboard_prompt(scene),
            base_url=base_url,
            timeout=timeout,
        )
        storyboard_txt.write_text(storyboard_text, encoding="utf-8")
        generate_image_to_path(
            api_key=api_key,
            prompt=build_interactive_comic_prompt(scene, storyboard_text),
            size=background_size,
            output_path=comic_raw,
            model=seedream_model,
            provider=provider,
            reference_images=[str(comic_ref_board)] if comic_ref_board else None,
        )
        comic_raw.replace(comic_png)
        update_progress(overall_progress, f"scene {scene_index}: interactive comic")
        return str(comic_png.resolve())

    with ThreadPoolExecutor(max_workers=max(2, scene_asset_workers)) as executor:
        background_future = executor.submit(generate_background_task)
        object_future = executor.submit(generate_objects_task)
        comic_future = executor.submit(generate_interactive_comic_task)
        character_futures = {
            executor.submit(generate_character_task, character, ref_board, related_objects): index
            for index, (character, ref_board, related_objects) in enumerate(character_jobs)
        }
        scene_manifest["background"] = background_future.result()
        ordered_characters: list[tuple[int, dict[str, Any]]] = []
        for future in as_completed(character_futures):
            ordered_characters.append((character_futures[future], future.result()))
        for _, character_payload in sorted(ordered_characters, key=lambda item: item[0]):
            scene_manifest["characters"].append(character_payload)
        scene_object_results = object_future.result()
        comic_result: str | None = None
        try:
            comic_result = comic_future.result()
        except Exception as exc:
            print(f"[comic] interactive comic generation failed for scene {scene_index}: {exc}")

    for result in scene_object_results:
        scene_manifest["objects"].append(result)

    if comic_result:
        scene_manifest["comic"] = comic_result
        scene_manifest["storyboard"] = str(storyboard_txt.resolve())

    if comic_ref_board and comic_ref_board.exists():
        comic_ref_board.unlink(missing_ok=True)
    if comic_raw.exists():
        comic_raw.unlink(missing_ok=True)

    save_json(scene_root / "manifest.json", scene_manifest)

    if dashscope_api_key:
        try:
            precompute_scene_placements(scene, scene_root, dashscope_api_key, base_url, timeout)
            update_progress(overall_progress, f"scene {scene_index}: placements")
        except Exception as e:
            print(f"[placements] precompute failed for scene {scene_index}: {e}")


def scene_work_units(scene: dict[str, Any], narrative_only: bool) -> int:
    units = 1
    if is_interactive_scene(scene["scene_type"]):
        units += 1  # background
        units += 1  # interactive comic (storyboard + 4-panel image)
        units += len(scene.get("characters", []))
        object_count = len(scene.get("objects", []))
        if object_count:
            units += math.ceil(object_count / 9)
    elif is_narrative_scene(scene["scene_type"]):
        units += 1
    return units


def collect_workflow_totals(
    story_payload: dict[str, Any],
    include_split: bool,
    include_global: bool,
    interactive_only: bool,
    narrative_only: bool,
) -> tuple[int, int]:
    global_content = story_payload.get("global_content", {})
    character_grids = math.ceil(len(global_content.get("characters", [])) / 9) if global_content.get("characters", []) else 0
    object_grids = math.ceil(len(global_content.get("objects", [])) / 9) if global_content.get("objects", []) else 0
    global_total = (character_grids + object_grids) if include_global else 0

    scenes = list(story_payload.get("scenes", []))
    if interactive_only:
        scenes = [scene for scene in scenes if is_interactive_scene(scene.get("scene_type"))]
    elif narrative_only:
        scenes = [scene for scene in scenes if is_narrative_scene(scene.get("scene_type"))]
    scene_total = sum(scene_work_units(scene, narrative_only=narrative_only) for scene in scenes)
    split_total = 1 if include_split else 0
    return split_total + global_total + scene_total, global_total


def run_workflow(args: argparse.Namespace) -> Path:
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    validate_seedream_size(args.asset_size, "Asset")
    validate_seedream_size(args.background_size, "Background")

    progress_callback = getattr(args, "progress_callback", None)

    if args.use_existing_scenes:
        parsed = load_json(args.scenes_json)
    else:
        story_text = load_story_text(args.text, args.input_file)
        parsed = None

    total_steps, _ = collect_workflow_totals(
        story_payload=parsed if parsed is not None else {"scenes": [], "global_content": {}},
        include_split=not args.use_existing_scenes,
        include_global=not args.use_existing_global,
        interactive_only=args.interactive_only,
        narrative_only=args.narrative_only,
    )
    overall_progress = tqdm(total=max(1, total_steps), desc="AI4Story workflow", unit="step", disable=args.no_progress)

    if not args.use_existing_scenes:
        overall_progress.set_postfix_str("splitting story")
        if progress_callback:
            progress_callback(10, "拆分场景中")
        parsed, _, _ = call_bailian_chat(
            api_key=args.dashscope_api_key,
            model=args.qwen_model,
            story_text=story_text,
            base_url=args.base_url,
            temperature=args.temperature,
            timeout=args.timeout,
            target_total_scenes=args.target_total_scenes if args.target_total_scenes > 0 else None,
            max_narrative_scenes=args.max_narrative_scenes if args.max_narrative_scenes > 0 else None,
            show_progress=not args.no_progress,
        )
        save_json(output_root / "story_scenes.json", parsed)
        total_steps, _ = collect_workflow_totals(
            story_payload=parsed,
            include_split=True,
            include_global=not args.use_existing_global,
            interactive_only=args.interactive_only,
            narrative_only=args.narrative_only,
        )
        overall_progress.total = max(1, total_steps)
        overall_progress.refresh()
        overall_progress.update(1)
        if progress_callback:
            progress_callback(20, "场景拆分完成")
    else:
        overall_progress.set_postfix_str("loading existing scenes")

    if args.use_existing_global:
        global_manifest = load_existing_global_manifest(output_root)
    else:
        if progress_callback:
            progress_callback(25, "生成全局角色资源")
        global_manifest = build_global_assets(
            story_payload=parsed,
            output_root=output_root,
            api_key=args.ark_api_key,
            provider=args.provider,
            seedream_model=args.seedream_model,
            asset_size=args.asset_size,
            overall_progress=overall_progress,
            show_progress=not args.no_progress,
            scene_asset_workers=args.asset_workers,
        )
        if progress_callback:
            progress_callback(40, "全局资源生成完成")

    scenes = list(parsed.get("scenes", []))
    if args.interactive_only:
        scenes = [scene for scene in scenes if is_interactive_scene(scene.get("scene_type"))]
    elif args.narrative_only:
        scenes = [scene for scene in scenes if is_narrative_scene(scene.get("scene_type"))]

    total_scenes = max(1, len(scenes))
    completed_scenes = 0
    scenes_lock = Lock()

    iterator = tqdm(total=len(scenes), desc="Building chapter assets", unit="scene", disable=args.no_progress)
    with ThreadPoolExecutor(max_workers=min(args.max_workers, max(1, len(scenes)))) as executor:
        future_map = {
            executor.submit(
                process_scene,
                scene=scene,
                output_root=output_root,
                global_manifest=global_manifest,
                dashscope_api_key=args.dashscope_api_key,
                api_key=args.ark_api_key,
                provider=args.provider,
                seedream_model=args.seedream_model,
                asset_size=args.asset_size,
                background_size=args.background_size,
                qwen_model=args.qwen_model,
                base_url=args.base_url,
                timeout=args.timeout,
                overall_progress=overall_progress,
                narrative_only=args.narrative_only,
                scene_asset_workers=args.asset_workers,
            ): scene
            for scene in scenes
        }
        for future in as_completed(future_map):
            scene = future_map[future]
            future.result()
            iterator.set_postfix_str(f"scene {scene.get('scene_index')}")
            iterator.update(1)
            if progress_callback:
                with scenes_lock:
                    completed_scenes += 1
                    pct = 40 + int(completed_scenes / total_scenes * 50)
                    progress_callback(pct, f"生成场景 {completed_scenes}/{total_scenes}")
    overall_progress.close()
    return output_root


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full AI4Story scene-to-assets workflow.")
    parser.add_argument("--text", default=None, help="Story text passed directly on the command line.")
    parser.add_argument("--input-file", default=None, help="Path to a UTF-8 text file containing the story.")
    parser.add_argument("--output-root", default=str(PROJECT_ROOT / "scenes"), help="Root directory for workflow outputs.")
    parser.add_argument("--scenes-json", default=str(PROJECT_ROOT / "scenes" / "story_scenes.json"), help="Path to an existing story_scenes.json file.")
    parser.add_argument("--use-existing-scenes", action="store_true", help="Skip scene splitting and load the existing scenes JSON.")
    parser.add_argument("--use-existing-global", action="store_true", help="Reuse the existing scenes/global assets and manifest.")
    parser.add_argument("--interactive-only", action="store_true", help="Only process interactive scenes during asset generation.")
    parser.add_argument("--narrative-only", action="store_true", help="Only process narrative scenes and skip all interactive-scene image generation.")
    parser.add_argument("--dashscope-api-key", default=os.getenv("DASHSCOPE_API_KEY"), help="DashScope API key for scene splitting.")
    parser.add_argument("--ark-api-key", default=os.getenv("ARK_API_KEY"), help="Volcengine ARK API key for image generation.")
    parser.add_argument("--qwen-model", default=DEFAULT_QWEN_MODEL, help="Qwen model for scene splitting.")
    parser.add_argument("--seedream-model", default=DEFAULT_SEEDREAM_MODEL, help="Seedream model for image generation.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Bailian OpenAI-compatible base URL.")
    parser.add_argument("--provider", default="ark", choices=["ark", "las"], help="Volcengine endpoint family.")
    parser.add_argument("--temperature", type=float, default=0.2, help="Scene-splitting sampling temperature.")
    parser.add_argument("--timeout", type=int, default=300, help="HTTP timeout in seconds.")
    parser.add_argument("--asset-size", default="2048x2048", help="Single foreground asset image size.")
    parser.add_argument("--background-size", default="2048x2048", help="Scene background image size used for every generated background.")
    parser.add_argument("--target-total-scenes", type=int, default=0, help="Optional scene-count hint. Use 0 for adaptive splitting.")
    parser.add_argument("--max-narrative-scenes", type=int, default=0, help="Optional narrative-scene hint. Use 0 for adaptive splitting.")
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS, help="Maximum number of scenes to generate in parallel.")
    parser.add_argument("--asset-workers", type=int, default=DEFAULT_MAX_WORKERS, help="Maximum parallel image tasks inside one scene or grid batch group.")
    parser.add_argument("--no-progress", action="store_true", help="Disable tqdm progress bars.")
    args = parser.parse_args()

    if args.interactive_only and args.narrative_only:
        raise ValueError("--interactive-only and --narrative-only cannot be used together.")
    if args.max_workers <= 0 or args.asset_workers <= 0:
        raise ValueError("--max-workers and --asset-workers must be positive integers.")

    if not args.use_existing_scenes and not args.dashscope_api_key:
        raise ValueError("Missing DashScope API key. Set DASHSCOPE_API_KEY or pass --dashscope-api-key.")
    if not args.interactive_only and not args.dashscope_api_key:
        raise ValueError("Narrative comic generation requires DashScope API key. Set DASHSCOPE_API_KEY or pass --dashscope-api-key.")
    if not args.ark_api_key:
        raise ValueError("Missing Volcengine API key. Set ARK_API_KEY or pass --ark-api-key.")

    output_root = run_workflow(args)
    print(f"Workflow completed. Outputs saved to: {output_root}")


if __name__ == "__main__":
    main()
