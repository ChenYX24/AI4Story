import json
import re
from typing import Any

import requests

from ..config import DASHSCOPE_API_KEY, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, QWEN_ASR_MODEL

# Chat / 文本生成默认走 LLM_BASE_URL（默认 mikaovo.ai） + LLM_MODEL（默认 gpt-5-4）。
# 同时保留 DashScope 配置：call_asr_audio 仍然必须命中 DashScope 自己的 ASR 接口。
BASE_URL = LLM_BASE_URL
DEFAULT_MODEL = LLM_MODEL
ASR_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


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
    if not LLM_API_KEY:
        raise QwenError("LLM_API_KEY (or DASHSCOPE_API_KEY) not set")
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
        "Authorization": f"Bearer {LLM_API_KEY}",
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
    if not LLM_API_KEY:
        raise QwenError("LLM_API_KEY (or DASHSCOPE_API_KEY) not set")
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
        "Authorization": f"Bearer {LLM_API_KEY}",
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


def call_chat(
    messages: list[dict[str, str]],
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.5,
    timeout: int = 60,
) -> str:
    """Send a full multi-turn messages list to the chat LLM and return the assistant reply."""
    if not LLM_API_KEY:
        raise QwenError("LLM_API_KEY (or DASHSCOPE_API_KEY) not set")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
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


def call_asr_audio(
    audio_data_url: str,
    *,
    model: str = QWEN_ASR_MODEL,
    timeout: int = 180,
) -> str:
    """Transcribe an audio data URL with DashScope's OpenAI-compatible ASR model."""
    if not DASHSCOPE_API_KEY:
        raise QwenError("DASHSCOPE_API_KEY not set")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_data_url,
                        },
                    }
                ],
            }
        ],
        "stream": False,
        "asr_options": {
            "enable_lid": True,
            "enable_itn": True,
        },
    }
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        f"{ASR_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise QwenError(f"HTTP {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(p.strip() for p in parts if p.strip())
    return str(content or "").strip()
