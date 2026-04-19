import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.image_generation.seedream_client import (
    DEFAULT_MODEL,
    build_grid_prompt,
    generate_image_to_path,
)

def load_input(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if "objects" not in data or not isinstance(data["objects"], list):
        raise ValueError("Input JSON must contain an 'objects' array.")
    if len(data["objects"]) != 9:
        raise ValueError("Input JSON must contain exactly 9 objects for the 3x3 grid.")
    normalized = []
    for index, item in enumerate(data["objects"], start=1):
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict) and isinstance(item.get("name"), str):
            name = item["name"].strip()
        else:
            raise ValueError(f"Invalid object at index {index}. Expected string or {{\"name\": \"...\"}}.")
        if not name:
            raise ValueError(f"Object name at index {index} is empty.")
        normalized.append(name)
    data["objects"] = normalized
    return data


def build_prompt(data: dict[str, Any]) -> str:
    objects = data["objects"]
    style = data.get("style", "hand-drawn illustration")
    extra = data.get("extra_prompt", "").strip()
    return build_grid_prompt(objects=objects, style=style, extra_prompt=extra)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a 3x3 object grid with Doubao Seedream.")
    parser.add_argument("--input", required=True, help="Path to input JSON.")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "outputs" / "images" / "grid.png"), help="Path to save the generated image.")
    parser.add_argument("--size", default="2048x2048", help="Output image size, e.g. 1024x1024 or 2048x2048.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Seedream model ID, not display name.")
    parser.add_argument("--api-key", default=None, help="ARK API key. Defaults to ARK_API_KEY env var.")
    parser.add_argument(
        "--provider",
        default="ark",
        choices=["ark", "las"],
        help="Which Volcengine endpoint family to use. 'ark' for Ark API, 'las' for LAS operator API.",
    )
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("ARK_API_KEY")
    if not api_key:
        raise ValueError("Missing API key. Set ARK_API_KEY or pass --api-key.")

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    data = load_input(input_path)
    prompt = build_prompt(data)
    saved_path = generate_image_to_path(
        api_key=api_key,
        prompt=prompt,
        size=args.size,
        output_path=output_path,
        model=args.model,
        provider=args.provider,
    )

    print("Prompt used:")
    print(prompt)
    print()
    print(f"Provider: {args.provider}")
    print(f"Model ID: {args.model}")
    print(f"Saved generated grid image to: {saved_path}")


if __name__ == "__main__":
    main()
