import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)


ARK_API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
LAS_API_URL = "https://operator.las.cn-beijing.volces.com/api/v1/online/images/generations"
LAS_API_URL_FALLBACK = "https://operator.las.cn-beijing.volces.com/api/v1/images/generations"
DEFAULT_MODEL = "doubao-seedream-5-0-lite-260128"


def build_grid_prompt(
    objects: list[str],
    style: str = "hand-drawn illustration",
    extra_prompt: str = "",
) -> str:
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
    prompt_parts = grid_note + cell_descriptions
    if extra_prompt.strip():
        prompt_parts.append(extra_prompt.strip())
    prompt_parts.append(f"Overall style keyword: {style}.")
    return " ".join(prompt_parts)


def local_image_to_data_url(path: str | Path) -> str:
    file_path = Path(path).resolve()
    mime_type, _ = mimetypes.guess_type(file_path.name)
    mime_type = mime_type or "image/png"
    encoded = base64.b64encode(file_path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def normalize_reference_images(reference_images: list[str | Path] | None) -> list[str]:
    normalized: list[str] = []
    for item in reference_images or []:
        value = str(item)
        if value.startswith("http://") or value.startswith("https://") or value.startswith("data:"):
            normalized.append(value)
        else:
            normalized.append(local_image_to_data_url(value))
    return normalized


def resolve_provider_url(provider: str) -> tuple[str, str | None]:
    if provider == "ark":
        return ARK_API_URL, None
    if provider == "las":
        return LAS_API_URL, LAS_API_URL_FALLBACK
    raise ValueError("provider must be 'ark' or 'las'.")


def generate_image_bytes(
    api_key: str,
    prompt: str,
    size: str,
    model: str = DEFAULT_MODEL,
    provider: str = "ark",
    reference_images: list[str | Path] | None = None,
    extra_payload: dict[str, Any] | None = None,
    timeout: int = 300,
) -> bytes:
    url, fallback_url = resolve_provider_url(provider)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "response_format": "b64_json",
        "output_format": "png",
        "watermark": False,
        "sequential_image_generation": "auto",
    }

    normalized_refs = normalize_reference_images(reference_images)
    if normalized_refs:
        # Inference from the official Seedream image-editing capability docs:
        # the API accepts an `image` input carrying the reference image.
        # When multiple local assets are needed, callers can provide a single
        # composed reference board or pass multiple values when supported.
        payload["image"] = normalized_refs if len(normalized_refs) > 1 else normalized_refs[0]

    if extra_payload:
        payload.update(extra_payload)

    ref_size_kb = sum(len(r) for r in normalized_refs) / 1024 if normalized_refs else 0
    log.info("[seedream] POST %s  model=%s size=%s refs=%d ref_data≈%.0fKB timeout=%ds",
             url, model, size, len(normalized_refs), ref_size_kb, timeout)

    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if response.status_code == 404 and fallback_url:
        log.info("[seedream] got 404, retrying with fallback URL")
        response = requests.post(fallback_url, headers=headers, json=payload, timeout=timeout)
    if response.status_code >= 400:
        print(f"[seedream] HTTP {response.status_code} — {response.text[:1000]}", flush=True)
        raise RuntimeError(
            f"Image generation failed with HTTP {response.status_code} at {response.url}\n"
            f"Response body:\n{response.text[:3000]}"
        )

    data = response.json()
    items = data.get("data") or []
    if not items or "b64_json" not in items[0]:
        raise RuntimeError(f"Unexpected API response: {str(data)[:1000]}")
    return base64.b64decode(items[0]["b64_json"])


def generate_image_to_path(
    api_key: str,
    prompt: str,
    size: str,
    output_path: str | Path,
    model: str = DEFAULT_MODEL,
    provider: str = "ark",
    reference_images: list[str | Path] | None = None,
    extra_payload: dict[str, Any] | None = None,
    timeout: int = 300,
) -> Path:
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        generate_image_bytes(
            api_key=api_key,
            prompt=prompt,
            size=size,
            model=model,
            provider=provider,
            reference_images=reference_images,
            extra_payload=extra_payload,
            timeout=timeout,
        )
    )
    return output
