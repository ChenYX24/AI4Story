import json
import re
from typing import Any

import requests

from ..config import DASHSCOPE_API_KEY

BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3.5-122b-a10b"


class QwenError(RuntimeError):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    """Try strict parse, then fall back to the first {...} block."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise QwenError(f"no JSON in response: {text[:400]}")
    return json.loads(m.group(0))


def call_json(
    prompt: str,
    *,
    system: str | None = None,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    timeout: int = 60,
    retries: int = 1,
) -> dict[str, Any]:
    if not DASHSCOPE_API_KEY:
        raise QwenError("DASHSCOPE_API_KEY not set")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    last_err: Exception | None = None
    for _ in range(retries + 1):
        try:
            resp = requests.post(
                f"{BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            if resp.status_code >= 400:
                raise QwenError(f"HTTP {resp.status_code}: {resp.text[:400]}")
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return _extract_json(content)
        except Exception as e:
            last_err = e
    raise QwenError(f"Qwen JSON call failed: {last_err}")


def call_text(
    prompt: str,
    *,
    system: str | None = None,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.5,
    timeout: int = 60,
) -> str:
    if not DASHSCOPE_API_KEY:
        raise QwenError("DASHSCOPE_API_KEY not set")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        f"{BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise QwenError(f"HTTP {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()
