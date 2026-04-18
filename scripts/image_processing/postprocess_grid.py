import argparse
import json
from collections import deque
from io import BytesIO
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageFilter
from tqdm import tqdm

try:
    from rembg import new_session, remove
except ImportError:
    new_session = None
    remove = None

try:
    import vtracer
except ImportError:
    vtracer = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def whiteness_distance(r: int, g: int, b: int) -> int:
    return (255 - r) + (255 - g) + (255 - b)


def is_background_candidate(r: int, g: int, b: int, tolerance: int, min_channel: int) -> bool:
    return r >= min_channel and g >= min_channel and b >= min_channel and whiteness_distance(r, g, b) <= tolerance


def remove_white_background_cell(
    image: Image.Image,
    tolerance: int,
    min_channel: int,
    soften_edge: int,
) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    background = [[False for _ in range(width)] for _ in range(height)]
    queue: deque[tuple[int, int]] = deque()

    def try_enqueue(x: int, y: int) -> None:
        if background[y][x]:
            return
        r, g, b, a = pixels[x, y]
        if a == 0:
            background[y][x] = True
            return
        if is_background_candidate(r, g, b, tolerance, min_channel):
            background[y][x] = True
            queue.append((x, y))

    for x in range(width):
        try_enqueue(x, 0)
        try_enqueue(x, height - 1)
    for y in range(height):
        try_enqueue(0, y)
        try_enqueue(width - 1, y)

    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
    while queue:
        x, y = queue.popleft()
        for dx, dy in directions:
            nx = x + dx
            ny = y + dy
            if 0 <= nx < width and 0 <= ny < height and not background[ny][nx]:
                r, g, b, a = pixels[nx, ny]
                if a == 0 or is_background_candidate(r, g, b, tolerance, min_channel):
                    background[ny][nx] = True
                    queue.append((nx, ny))

    for y in range(height):
        for x in range(width):
            if background[y][x]:
                pixels[x, y] = (255, 255, 255, 0)
                continue

            r, g, b, a = pixels[x, y]
            if a == 0:
                continue

            # Keep foreground strokes, but soften nearly-white anti-aliased edges.
            if is_background_candidate(r, g, b, tolerance + soften_edge, min_channel - 10):
                pixels[x, y] = (r, g, b, max(0, a // 2))

    return rgba


def remove_white_background(
    image: Image.Image,
    tolerance: int,
    min_channel: int,
    soften_edge: int,
    show_progress: bool,
) -> Image.Image:
    rgba = image.convert("RGBA")
    result = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
    boxes = cell_boxes(rgba.width, rgba.height)
    iterator = tqdm(boxes, desc="Removing background", unit="cell") if show_progress else boxes
    for box in iterator:
        cell = rgba.crop(box)
        processed = remove_white_background_cell(cell, tolerance, min_channel, soften_edge)
        result.paste(processed, box)
    return result


def remove_white_background_single(
    image: Image.Image,
    tolerance: int,
    min_channel: int,
    soften_edge: int,
) -> Image.Image:
    return remove_white_background_cell(
        image=image,
        tolerance=tolerance,
        min_channel=min_channel,
        soften_edge=soften_edge,
    )


def remove_background_with_rembg(
    image: Image.Image,
    model_name: str,
    alpha_matting: bool,
    show_progress: bool,
) -> Image.Image:
    if remove is None or new_session is None:
        raise RuntimeError(
            "rembg is not installed. Run 'pip install rembg onnxruntime' or switch "
            "--bg-removal-method to 'threshold'."
        )

    rgba = image.convert("RGBA")
    result = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
    session = new_session(model_name)
    boxes = cell_boxes(rgba.width, rgba.height)
    iterator = tqdm(boxes, desc="Removing background", unit="cell") if show_progress else boxes

    for box in iterator:
        cell = rgba.crop(box)
        output = remove(
            cell,
            session=session,
            alpha_matting=alpha_matting,
        )
        processed = output if isinstance(output, Image.Image) else Image.open(BytesIO(output)).convert("RGBA")
        result.paste(processed, box)

    return result


def remove_background_with_rembg_single(
    image: Image.Image,
    model_name: str,
    alpha_matting: bool,
) -> Image.Image:
    if remove is None or new_session is None:
        raise RuntimeError(
            "rembg is not installed. Run 'pip install rembg onnxruntime' or switch "
            "--bg-removal-method to 'threshold'."
        )

    session = new_session(model_name)
    output = remove(
        image.convert("RGBA"),
        session=session,
        alpha_matting=alpha_matting,
    )
    return output if isinstance(output, Image.Image) else Image.open(BytesIO(output)).convert("RGBA")


def cell_boxes(width: int, height: int) -> list[tuple[int, int, int, int]]:
    cell_w = width // 3
    cell_h = height // 3
    boxes = []
    for row in range(3):
        for col in range(3):
            left = col * cell_w
            top = row * cell_h
            right = (col + 1) * cell_w if col < 2 else width
            bottom = (row + 1) * cell_h if row < 2 else height
            boxes.append((left, top, right, bottom))
    return boxes


def alpha_mask(image: Image.Image, alpha_threshold: int) -> list[list[int]]:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    mask = [[0 for _ in range(width)] for _ in range(height)]
    for y in range(height):
        for x in range(width):
            mask[y][x] = 1 if pixels[x, y][3] > alpha_threshold else 0
    return mask


def largest_component_bbox(mask: list[list[int]]) -> tuple[int, int, int, int] | None:
    height = len(mask)
    width = len(mask[0]) if height else 0
    visited = [[False for _ in range(width)] for _ in range(height)]
    best_area = 0
    best_bbox = None
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))

    for y in range(height):
        for x in range(width):
            if not mask[y][x] or visited[y][x]:
                continue
            queue: deque[tuple[int, int]] = deque([(x, y)])
            visited[y][x] = True
            area = 0
            min_x = max_x = x
            min_y = max_y = y
            while queue:
                cx, cy = queue.popleft()
                area += 1
                min_x = min(min_x, cx)
                min_y = min(min_y, cy)
                max_x = max(max_x, cx)
                max_y = max(max_y, cy)
                for dx, dy in directions:
                    nx = cx + dx
                    ny = cy + dy
                    if 0 <= nx < width and 0 <= ny < height and mask[ny][nx] and not visited[ny][nx]:
                        visited[ny][nx] = True
                        queue.append((nx, ny))
            if area > best_area:
                best_area = area
                best_bbox = (min_x, min_y, max_x + 1, max_y + 1)
    return best_bbox


def add_padding(bbox: tuple[int, int, int, int], width: int, height: int, padding: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


def add_white_outline(image: Image.Image, outline_width: int, outline_blur: int) -> Image.Image:
    if outline_width <= 0:
        return image.convert("RGBA")

    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")

    expanded = alpha
    for _ in range(outline_width):
        expanded = expanded.filter(ImageFilter.MaxFilter(3))

    if outline_blur > 0:
        expanded = expanded.filter(ImageFilter.GaussianBlur(outline_blur))

    outline_mask = ImageChops.subtract(expanded, alpha)
    outline_layer = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
    outline_layer.putalpha(outline_mask)
    return Image.alpha_composite(outline_layer, rgba)


def save_vector_svg(
    image: Image.Image,
    png_path: Path,
    svg_path: Path,
    colormode: str,
    hierarchical: str,
    mode: str,
) -> None:
    if vtracer is None:
        raise RuntimeError(
            "vtracer is not installed. Run 'pip install vtracer' and rerun the script."
        )

    image.save(png_path)
    vtracer.convert_image_to_svg_py(
        str(png_path),
        str(svg_path),
        colormode=colormode,
        hierarchical=hierarchical,
        mode=mode,
    )


def remove_background_dispatch(
    image: Image.Image,
    method: str,
    rembg_model: str,
    rembg_alpha_matting: bool,
    white_tolerance: int,
    white_min_channel: int,
    soften_edge: int,
    show_progress: bool,
    split_grid: bool = True,
) -> Image.Image:
    if method == "rembg":
        if split_grid:
            return remove_background_with_rembg(
                image,
                model_name=rembg_model,
                alpha_matting=rembg_alpha_matting,
                show_progress=show_progress,
            )
        return remove_background_with_rembg_single(
            image,
            model_name=rembg_model,
            alpha_matting=rembg_alpha_matting,
        )
    if split_grid:
        return remove_white_background(
            image,
            tolerance=white_tolerance,
            min_channel=white_min_channel,
            soften_edge=soften_edge,
            show_progress=show_progress,
        )
    return remove_white_background_single(
        image,
        tolerance=white_tolerance,
        min_channel=white_min_channel,
        soften_edge=soften_edge,
    )


def crop_single_foreground(image: Image.Image, alpha_threshold: int, crop_padding: int) -> Image.Image:
    mask = alpha_mask(image, alpha_threshold)
    bbox = largest_component_bbox(mask)
    if bbox is None:
        return image.convert("RGBA")
    padded_bbox = add_padding(bbox, image.width, image.height, crop_padding)
    return image.crop(padded_bbox).convert("RGBA")


def postprocess_single_asset(
    input_path: str | Path,
    png_output_path: str | Path,
    svg_output_path: str | Path,
    transparent_output_path: str | Path | None = None,
    bg_removal_method: str = "rembg",
    rembg_model: str = "u2net",
    rembg_alpha_matting: bool = True,
    white_tolerance: int = 42,
    white_min_channel: int = 235,
    soften_edge: int = 18,
    alpha_threshold: int = 8,
    crop_padding: int = 12,
    outline_width: int = 10,
    outline_blur: int = 1,
    svg_colormode: str = "color",
    svg_hierarchical: str = "stacked",
    svg_mode: str = "spline",
) -> dict[str, str | int]:
    image = Image.open(Path(input_path).resolve())
    transparent = remove_background_dispatch(
        image=image,
        method=bg_removal_method,
        rembg_model=rembg_model,
        rembg_alpha_matting=rembg_alpha_matting,
        white_tolerance=white_tolerance,
        white_min_channel=white_min_channel,
        soften_edge=soften_edge,
        show_progress=False,
        split_grid=False,
    )
    if transparent_output_path is not None:
        transparent_path = Path(transparent_output_path).resolve()
        transparent_path.parent.mkdir(parents=True, exist_ok=True)
        transparent.save(transparent_path)

    cropped = crop_single_foreground(transparent, alpha_threshold=alpha_threshold, crop_padding=crop_padding)
    outlined = add_white_outline(cropped, outline_width=outline_width, outline_blur=outline_blur)

    png_path = Path(png_output_path).resolve()
    svg_path = Path(svg_output_path).resolve()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    save_vector_svg(
        outlined,
        png_path=png_path,
        svg_path=svg_path,
        colormode=svg_colormode,
        hierarchical=svg_hierarchical,
        mode=svg_mode,
    )
    return {
        "png": str(png_path),
        "svg": str(svg_path),
        "width": outlined.width,
        "height": outlined.height,
    }


def export_cells(
    image: Image.Image,
    output_dir: Path,
    object_names: Iterable[str] | None,
    alpha_threshold: int,
    crop_padding: int,
    outline_width: int,
    outline_blur: int,
    svg_colormode: str,
    svg_hierarchical: str,
    svg_mode: str,
    show_progress: bool,
) -> list[dict[str, str | int]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    width, height = image.size
    boxes = cell_boxes(width, height)
    names = list(object_names or [])
    manifest: list[dict[str, str | int]] = []

    indexed_boxes = list(enumerate(boxes, start=1))
    iterator = tqdm(indexed_boxes, desc="Exporting cells", unit="cell") if show_progress else indexed_boxes

    for index, box in iterator:
        cell = image.crop(box)
        mask = alpha_mask(cell, alpha_threshold)
        bbox = largest_component_bbox(mask)
        if bbox is None:
            cropped = cell
        else:
            padded_bbox = add_padding(bbox, cell.width, cell.height, crop_padding)
            cropped = cell.crop(padded_bbox)
        cropped = add_white_outline(cropped, outline_width=outline_width, outline_blur=outline_blur)

        stem = f"{index:02d}"
        if index <= len(names):
            safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in names[index - 1]).strip("_")
            if safe_name:
                stem = f"{stem}_{safe_name}"

        png_path = output_dir / f"{stem}.png"
        svg_path = output_dir / f"{stem}.svg"
        save_vector_svg(
            cropped,
            png_path=png_path,
            svg_path=svg_path,
            colormode=svg_colormode,
            hierarchical=svg_hierarchical,
            mode=svg_mode,
        )

        manifest.append(
            {
                "index": index,
                "png": str(png_path.resolve()),
                "svg": str(svg_path.resolve()),
                "width": cropped.width,
                "height": cropped.height,
            }
        )

    return manifest


def load_object_names(json_path: Path | None) -> list[str]:
    if json_path is None:
        return []
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    objects = data.get("objects", [])
    names = []
    for item in objects:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove white background and split a 3x3 grid image.")
    parser.add_argument("--input", required=True, help="Path to the source grid image.")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "outputs" / "images" / "extracted"), help="Directory for extracted PNG and SVG files.")
    parser.add_argument("--input-json", default=None, help="Optional input JSON with object names.")
    parser.add_argument(
        "--bg-removal-method",
        default="rembg",
        choices=["threshold", "rembg"],
        help="Background removal backend. 'threshold' is fast and deterministic, 'rembg' uses a segmentation model.",
    )
    parser.add_argument("--rembg-model", default="u2net", help="rembg model name, such as u2net or isnet-general-use.")
    parser.add_argument(
        "--rembg-alpha-matting",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable rembg alpha matting for cleaner fine edges.",
    )
    parser.add_argument("--white-tolerance", type=int, default=42, help="How close to white a pixel must be to become transparent.")
    parser.add_argument("--white-min-channel", type=int, default=235, help="Minimum RGB channel value for a pixel to be considered white background.")
    parser.add_argument("--soften-edge", type=int, default=18, help="Extra tolerance used to soften near-white anti-aliased edges.")
    parser.add_argument("--alpha-threshold", type=int, default=8, help="Alpha threshold used to detect foreground pixels.")
    parser.add_argument("--crop-padding", type=int, default=12, help="Extra padding around detected objects.")
    parser.add_argument("--outline-width", type=int, default=10, help="White outline thickness around each extracted object.")
    parser.add_argument("--outline-blur", type=int, default=1, help="Slight blur radius for a smoother sticker-like white outline.")
    parser.add_argument("--svg-colormode", default="color", choices=["color", "binary"], help="VTracer color mode for SVG export.")
    parser.add_argument("--svg-hierarchical", default="stacked", choices=["stacked", "cutout"], help="VTracer hierarchical mode.")
    parser.add_argument("--svg-mode", default="spline", choices=["spline", "polygon", "none"], help="VTracer path fitting mode.")
    parser.add_argument("--transparent-grid-output", default=str(PROJECT_ROOT / "outputs" / "images" / "grid_transparent.png"), help="Path for the whole transparent grid PNG.")
    parser.add_argument("--no-progress", action="store_true", help="Disable tqdm progress bars.")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()
    transparent_grid_path = Path(args.transparent_grid_output).resolve()
    transparent_grid_path.parent.mkdir(parents=True, exist_ok=True)
    show_progress = not args.no_progress

    image = Image.open(input_path)
    transparent = remove_background_dispatch(
        image=image,
        method=args.bg_removal_method,
        rembg_model=args.rembg_model,
        rembg_alpha_matting=args.rembg_alpha_matting,
        white_tolerance=args.white_tolerance,
        white_min_channel=args.white_min_channel,
        soften_edge=args.soften_edge,
        show_progress=show_progress,
    )
    transparent.save(transparent_grid_path)

    object_names = load_object_names(Path(args.input_json).resolve()) if args.input_json else []
    manifest = export_cells(
        transparent,
        output_dir=output_dir,
        object_names=object_names,
        alpha_threshold=args.alpha_threshold,
        crop_padding=args.crop_padding,
        outline_width=args.outline_width,
        outline_blur=args.outline_blur,
        svg_colormode=args.svg_colormode,
        svg_hierarchical=args.svg_hierarchical,
        svg_mode=args.svg_mode,
        show_progress=show_progress,
    )

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Saved transparent grid to: {transparent_grid_path}")
    print(f"Saved extracted assets to: {output_dir}")
    print(f"Saved manifest to: {manifest_path}")


if __name__ == "__main__":
    main()
