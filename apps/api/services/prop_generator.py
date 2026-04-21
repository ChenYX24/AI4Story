import io
import re
import sys
from pathlib import Path

from PIL import Image

from ..config import (
    ARK_API_KEY,
    OUTPUTS_ROOT,
    PROJECT_ROOT,
    SEEDREAM_MODEL,
    SEEDREAM_PROVIDER,
    SEEDREAM_SIZE,
    SEEDREAM_TIMEOUT,
)

sys.path.insert(0, str(PROJECT_ROOT))
from scripts.image_generation.seedream_client import (  # noqa: E402
    build_grid_prompt,
    generate_image_bytes,
)
from scripts.image_processing.postprocess_grid import (  # noqa: E402
    cell_boxes,
    remove_background_with_rembg,
    remove_background_with_rembg_single,
)

from .qwen_service import QwenError, call_json  # noqa: E402

REMBG_MODEL = "isnet-general-use"


def _slug(name: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", name.strip())
    return cleaned.strip("_") or "prop"


def _build_prompt(name: str, description: str | None) -> str:
    extra = (description or "").strip()
    parts = [
        f'Create one single "{name}" object illustration.',
        "Centered on pure white background.",
        "Hand-drawn colored pencil children's storybook style.",
        "No shadows on the background.",
        "No text, no labels, no decorations.",
        "Leave generous white space around the object so it can be cut out cleanly.",
        "Soft warm colors, clear outlines, whimsical and friendly.",
    ]
    if extra:
        parts.append(f"Extra detail: {extra}")
    return " ".join(parts)


def create_custom_prop(
    session_id: str,
    name: str,
    description: str | None,
) -> tuple[str, Path]:
    if not ARK_API_KEY:
        raise RuntimeError("ARK_API_KEY 未配置，无法生成物品")

    raw_png = generate_image_bytes(
        api_key=ARK_API_KEY,
        prompt=_build_prompt(name, description),
        size=SEEDREAM_SIZE,
        model=SEEDREAM_MODEL,
        provider=SEEDREAM_PROVIDER,
        timeout=SEEDREAM_TIMEOUT,
    )

    try:
        img = Image.open(io.BytesIO(raw_png)).convert("RGBA")
        transparent = remove_background_with_rembg_single(
            image=img,
            model_name=REMBG_MODEL,
            alpha_matting=True,
        )
        transparent = _crop_to_content(transparent)
        out_bytes_buf = io.BytesIO()
        transparent.save(out_bytes_buf, format="PNG")
        out_bytes = out_bytes_buf.getvalue()
    except Exception as e:
        print(f"[prop_generator] rembg failed, using raw PNG: {e}")
        out_bytes = raw_png

    session_dir = OUTPUTS_ROOT / session_id / "custom_props"
    session_dir.mkdir(parents=True, exist_ok=True)
    slug = _slug(name)
    out_path = session_dir / f"{slug}.png"
    # avoid clobber: append suffix if exists
    i = 2
    while out_path.exists():
        out_path = session_dir / f"{slug}_{i}.png"
        i += 1
    out_path.write_bytes(out_bytes)
    url = f"/outputs/{session_id}/custom_props/{out_path.name}"
    return url, out_path


def _crop_to_content(img: Image.Image, padding: int = 24) -> Image.Image:
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    if not bbox:
        return img
    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(img.width, right + padding)
    bottom = min(img.height, bottom + padding)
    return img.crop((left, top, right, bottom))


def parse_items_from_text(text: str, existing_names: list[str] | None = None) -> list[dict]:
    """Use Qwen to split a free-text request into a list of {name, description}.

    - Determines how many distinct items the user wants
    - Gives each a concise 2-6-character kid-friendly name
    - Renames awkward phrasings into clean object labels
    - Avoids colliding with existing_names
    """
    clean = (text or "").strip()
    if not clean:
        raise RuntimeError("没说要创造什么物品")

    existing = "、".join(existing_names or []) or "（无）"
    prompt = (
        "小朋友想在互动故事场景里创造一些新物品。请把下面这段自然语言描述解析成结构化的物品列表。\n"
        "规则：\n"
        "1. 识别用户想要的物品数量（1 到 9 之间）。每个独立物品产生一个列表元素。\n"
        "2. 每个物品给一个简洁、可爱、适合儿童绘本的名字（2-6 个汉字），必要时对不通顺的描述进行重命名。\n"
        "3. 如果用户描述了物品的外观、颜色、材质、功能，写到 description（10-40 字内），否则留空字符串。\n"
        "4. 不要输出任何场景中已存在的名字；如果冲突，加一个形容词以区分。\n"
        f"5. 场景中已有：{existing}\n\n"
        "严格输出 JSON，不要代码块标记，不要解释：\n"
        '{"items":[{"name":"...","description":"..."}]}\n\n'
        f"用户的描述：{clean}"
    )
    try:
        parsed = call_json(prompt, temperature=0.2, timeout=30)
    except QwenError as e:
        raise RuntimeError(f"解析物品失败：{e}") from e

    raw = parsed.get("items") or []
    items: list[dict] = []
    seen = set(existing_names or [])
    for it in raw[:9]:
        name = str(it.get("name", "")).strip()
        desc = str(it.get("description", "")).strip()
        if not name:
            continue
        # ensure uniqueness against existing + already-added
        base = name
        k = 2
        while name in seen:
            name = f"{base}{k}"
            k += 1
        seen.add(name)
        items.append({"name": name, "description": desc or None})
    if not items:
        raise RuntimeError("没识别到要创造的物品，请再说一次")
    return items


def smart_create_props(
    session_id: str,
    scene_idx: int,
    text: str,
    existing_names: list[str] | None = None,
) -> tuple[list[str], list[dict]]:
    """Full pipeline: parse text → route to single or batch generator."""
    items = parse_items_from_text(text, existing_names=existing_names)
    parsed_names = [it["name"] for it in items]
    if len(items) == 1:
        url, _ = create_custom_prop(session_id, items[0]["name"], items[0].get("description"))
        return parsed_names, [{"name": items[0]["name"], "url": url}]
    return parsed_names, create_custom_props_batch(session_id, items)


def create_custom_props_batch(
    session_id: str,
    items: list[dict],
) -> list[dict]:
    """Generate up to 9 props in one Seedream 3x3 grid call.

    items: [{"name": str, "description": str|None}]
    returns: [{"name": str, "url": str}]
    """
    if not items:
        return []
    if not ARK_API_KEY:
        raise RuntimeError("ARK_API_KEY 未配置，无法生成物品")

    items = items[:9]
    real_count = len(items)
    names = [it.get("name", "").strip() for it in items]
    if any(not n for n in names):
        raise RuntimeError("物品名不能为空")

    # pad to 9 with blank placeholders so Seedream leaves those cells empty
    padded_names = names + ["__empty_slot__"] * (9 - real_count)
    cell_descriptions = []
    for i, it in enumerate(items):
        desc = (it.get("description") or "").strip()
        nm = it["name"].strip()
        cell_descriptions.append(f"{nm}: {desc}" if desc else nm)

    prompt = build_grid_prompt(
        cell_descriptions + ["leave empty"] * (9 - real_count),
        style="hand-drawn children's storybook colored pencil illustration",
        extra_prompt=(
            "Each cell must hold exactly one object on pure white background, "
            "centered with generous padding, no shadows, no text. "
            "Warm soft colors consistent with a 5-year-old children's book."
        ),
    )

    raw_png = generate_image_bytes(
        api_key=ARK_API_KEY,
        prompt=prompt,
        size=SEEDREAM_SIZE,
        model=SEEDREAM_MODEL,
        provider=SEEDREAM_PROVIDER,
        timeout=SEEDREAM_TIMEOUT,
    )

    try:
        full_img = Image.open(io.BytesIO(raw_png)).convert("RGBA")
        transparent = remove_background_with_rembg(
            full_img,
            model_name=REMBG_MODEL,
            alpha_matting=True,
            show_progress=False,
        )
    except Exception as e:
        print(f"[prop_generator] rembg failed for grid: {e}")
        transparent = Image.open(io.BytesIO(raw_png)).convert("RGBA")

    session_dir = OUTPUTS_ROOT / session_id / "custom_props"
    session_dir.mkdir(parents=True, exist_ok=True)

    boxes = cell_boxes(transparent.width, transparent.height)
    results: list[dict] = []
    for i in range(real_count):
        cell = transparent.crop(boxes[i])
        cell = _crop_to_content(cell)
        slug = _slug(names[i])
        out = session_dir / f"{slug}.png"
        k = 2
        while out.exists():
            out = session_dir / f"{slug}_{k}.png"
            k += 1
        cell.save(out, "PNG")
        results.append({
            "name": names[i],
            "url": f"/outputs/{session_id}/custom_props/{out.name}",
        })
    return results
