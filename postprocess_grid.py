import argparse
import base64
import json
from collections import deque
from io import BytesIO
from pathlib import Path
from typing import Iterable

from PIL import Image


def whiteness_distance(r: int, g: int, b: int) -> int:
    return (255 - r) + (255 - g) + (255 - b)


def channel_distance(color_a: tuple[int, int, int], color_b: tuple[int, int, int]) -> int:
    return max(abs(color_a[0] - color_b[0]), abs(color_a[1] - color_b[1]), abs(color_a[2] - color_b[2]))


def sample_border_background(image: Image.Image, border_width: int) -> tuple[int, int, int]:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    samples: list[tuple[int, int, int]] = []

    for y in range(height):
        for x in range(width):
            if x < border_width or y < border_width or x >= width - border_width or y >= height - border_width:
                r, g, b, a = pixels[x, y]
                if a > 0:
                    samples.append((r, g, b))

    if not samples:
        return (255, 255, 255)

    samples.sort(key=lambda c: c[0] + c[1] + c[2], reverse=True)
    bright_samples = samples[: max(16, len(samples) // 3)]
    rs = sorted(c[0] for c in bright_samples)
    gs = sorted(c[1] for c in bright_samples)
    bs = sorted(c[2] for c in bright_samples)
    mid = len(bright_samples) // 2
    return (rs[mid], gs[mid], bs[mid])


def is_background_candidate(
    r: int,
    g: int,
    b: int,
    background_rgb: tuple[int, int, int],
    tolerance: int,
    min_channel: int,
) -> bool:
    return (
        r >= min_channel
        and g >= min_channel
        and b >= min_channel
        and channel_distance((r, g, b), background_rgb) <= tolerance
    )


def remove_white_background_cell(
    image: Image.Image,
    tolerance: int,
    min_channel: int,
    border_width: int,
    soften_edge: int,
) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    background = [[False for _ in range(width)] for _ in range(height)]
    queue: deque[tuple[int, int]] = deque()
    background_rgb = sample_border_background(rgba, border_width)
    expand_tolerance = tolerance + max(0, soften_edge)

    def try_enqueue(x: int, y: int) -> None:
        if background[y][x]:
            return
        r, g, b, a = pixels[x, y]
        if a == 0:
            background[y][x] = True
            return
        if is_background_candidate(r, g, b, background_rgb, tolerance, min_channel):
            background[y][x] = True
            queue.append((x, y))

    for x in range(width):
        try_enqueue(x, 0)
        try_enqueue(x, height - 1)
    for y in range(height):
        try_enqueue(0, y)
        try_enqueue(width - 1, y)

    directions = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
    while queue:
        x, y = queue.popleft()
        for dx, dy in directions:
            nx = x + dx
            ny = y + dy
            if 0 <= nx < width and 0 <= ny < height and not background[ny][nx]:
                r, g, b, a = pixels[nx, ny]
                if a == 0 or is_background_candidate(r, g, b, background_rgb, expand_tolerance, min_channel):
                    background[ny][nx] = True
                    queue.append((nx, ny))

    for y in range(height):
        for x in range(width):
            if background[y][x]:
                pixels[x, y] = (255, 255, 255, 0)

    return rgba


def remove_white_background(
    image: Image.Image,
    tolerance: int,
    min_channel: int,
    border_width: int,
    soften_edge: int,
) -> Image.Image:
    rgba = image.convert("RGBA")
    result = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
    for box in cell_boxes(rgba.width, rgba.height):
        cell = rgba.crop(box)
        processed = remove_white_background_cell(cell, tolerance, min_channel, border_width, soften_edge)
        result.paste(processed, box)
    return result


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


def component_bboxes(mask: list[list[int]]) -> list[tuple[int, int, int, int, int]]:
    height = len(mask)
    width = len(mask[0]) if height else 0
    visited = [[False for _ in range(width)] for _ in range(height)]
    boxes: list[tuple[int, int, int, int, int]] = []
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))

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
            boxes.append((min_x, min_y, max_x + 1, max_y + 1, area))
    return boxes


def foreground_bbox(mask: list[list[int]], min_component_area: int) -> tuple[int, int, int, int] | None:
    boxes = component_bboxes(mask)
    kept = [box for box in boxes if box[4] >= min_component_area]
    if not kept and boxes:
        kept = [max(boxes, key=lambda box: box[4])]
    if not kept:
        return None
    left = min(box[0] for box in kept)
    top = min(box[1] for box in kept)
    right = max(box[2] for box in kept)
    bottom = max(box[3] for box in kept)
    return (left, top, right, bottom)


def add_padding(bbox: tuple[int, int, int, int], width: int, height: int, padding: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


def png_bytes(image: Image.Image) -> bytes:
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def save_embedded_svg(image: Image.Image, target_path: Path) -> None:
    width, height = image.size
    encoded = base64.b64encode(png_bytes(image)).decode("ascii")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'  <image width="{width}" height="{height}" href="data:image/png;base64,{encoded}"/>\n'
        f"</svg>\n"
    )
    target_path.write_text(svg, encoding="utf-8")


def export_cells(
    image: Image.Image,
    output_dir: Path,
    object_names: Iterable[str] | None,
    alpha_threshold: int,
    crop_padding: int,
) -> list[dict[str, str | int]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    width, height = image.size
    boxes = cell_boxes(width, height)
    names = list(object_names or [])
    manifest: list[dict[str, str | int]] = []

    for index, box in enumerate(boxes, start=1):
        cell = image.crop(box)
        mask = alpha_mask(cell, alpha_threshold)
        min_component_area = max(32, (cell.width * cell.height) // 5000)
        bbox = foreground_bbox(mask, min_component_area)
        if bbox is None:
            cropped = cell
        else:
            padded_bbox = add_padding(bbox, cell.width, cell.height, crop_padding)
            cropped = cell.crop(padded_bbox)

        stem = f"{index:02d}"
        if index <= len(names):
            safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in names[index - 1]).strip("_")
            if safe_name:
                stem = f"{stem}_{safe_name}"

        png_path = output_dir / f"{stem}.png"
        svg_path = output_dir / f"{stem}.svg"
        cropped.save(png_path)
        save_embedded_svg(cropped, svg_path)

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
    parser.add_argument("--output-dir", default="outputs/extracted", help="Directory for extracted PNG and SVG files.")
    parser.add_argument("--input-json", default=None, help="Optional input JSON with object names.")
    parser.add_argument("--white-tolerance", type=int, default=26, help="Maximum channel difference from the sampled border background.")
    parser.add_argument("--white-min-channel", type=int, default=240, help="Minimum RGB channel value for a pixel to be considered bright background.")
    parser.add_argument("--border-width", type=int, default=8, help="How many pixels from each cell border are sampled to estimate background color.")
    parser.add_argument("--soften-edge", type=int, default=8, help="Extra expansion tolerance for border-connected background only.")
    parser.add_argument("--alpha-threshold", type=int, default=8, help="Alpha threshold used to detect foreground pixels.")
    parser.add_argument("--crop-padding", type=int, default=12, help="Extra padding around detected objects.")
    parser.add_argument("--transparent-grid-output", default="outputs/grid_transparent.png", help="Path for the whole transparent grid PNG.")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()
    transparent_grid_path = Path(args.transparent_grid_output).resolve()
    transparent_grid_path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.open(input_path)
    transparent = remove_white_background(
        image,
        tolerance=args.white_tolerance,
        min_channel=args.white_min_channel,
        border_width=args.border_width,
        soften_edge=args.soften_edge,
    )
    transparent.save(transparent_grid_path)

    object_names = load_object_names(Path(args.input_json).resolve()) if args.input_json else []
    manifest = export_cells(
        transparent,
        output_dir=output_dir,
        object_names=object_names,
        alpha_threshold=args.alpha_threshold,
        crop_padding=args.crop_padding,
    )

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Saved transparent grid to: {transparent_grid_path}")
    print(f"Saved extracted assets to: {output_dir}")
    print(f"Saved manifest to: {manifest_path}")


if __name__ == "__main__":
    main()
