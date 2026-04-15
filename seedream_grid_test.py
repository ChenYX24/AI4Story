import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any

import requests


ARK_API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
LAS_API_URL = "https://operator.las.cn-beijing.volces.com/api/v1/online/images/generations"
LAS_API_URL_FALLBACK = "https://operator.las.cn-beijing.volces.com/api/v1/images/generations"
DEFAULT_MODEL = "doubao-seedream-5-0-lite-260128"


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
    grid_note = [
        "Create one single image arranged as a 3x3 equal-sized grid.",
        "Pure white background.",
        "All nine cells must be exactly the same size and aligned cleanly.",
        "Place exactly one object in each cell.",
        "Keep all objects centered in their own cells and do not let them overlap grid boundaries.",
        "Use a consistent hand-drawn illustration style across all nine objects.",
        "Keep lighting, line weight, and rendering style consistent.",
        "No extra decorations, no text, no labels, no shadows outside the object.",
        "Leave enough white space around each object so it can be cut out cleanly.",
        "The grid lines themselves should not be visible.",
    ]
    cell_descriptions = [f"Cell {idx}: {name}." for idx, name in enumerate(objects, start=1)]
    extra = data.get("extra_prompt", "").strip()
    prompt_parts = grid_note + cell_descriptions
    if extra:
        prompt_parts.append(extra)
    prompt_parts.append(f"Overall style keyword: {style}.")
    return " ".join(prompt_parts)


def request_seedream_image(
    api_key: str,
    prompt: str,
    size: str,
    model: str,
    output_path: Path,
    provider: str,
) -> Path:
    if provider == "ark":
        url = ARK_API_URL
    elif provider == "las":
        url = LAS_API_URL
    else:
        raise ValueError("provider must be 'ark' or 'las'.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "response_format": "b64_json",
        "output_format": "png",
        "watermark": False,
        "sequential_image_generation": "auto",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=300)
    if response.status_code == 404 and provider == "las":
        response = requests.post(LAS_API_URL_FALLBACK, headers=headers, json=payload, timeout=300)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Image generation failed with HTTP {response.status_code} at {response.url}\n"
            f"Response body:\n{response.text[:2000]}"
        )
    data = response.json()
    items = data.get("data") or []
    if not items or "b64_json" not in items[0]:
        raise RuntimeError(f"Unexpected API response: {json.dumps(data, ensure_ascii=False)[:1000]}")
    image_bytes = base64.b64decode(items[0]["b64_json"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a 3x3 object grid with Doubao Seedream.")
    parser.add_argument("--input", required=True, help="Path to input JSON.")
    parser.add_argument("--output", default="outputs/grid.png", help="Path to save the generated image.")
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
    saved_path = request_seedream_image(api_key, prompt, args.size, args.model, output_path, args.provider)

    print("Prompt used:")
    print(prompt)
    print()
    print(f"Provider: {args.provider}")
    print(f"Model ID: {args.model}")
    print(f"Saved generated grid image to: {saved_path}")


if __name__ == "__main__":
    main()
