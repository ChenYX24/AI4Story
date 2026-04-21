import base64
import re

import requests

from ..config import (
    XIAOMI_TTS_API_KEY,
    XIAOMI_TTS_BASE_URL,
    XIAOMI_TTS_FORMAT,
    XIAOMI_TTS_MODEL,
    XIAOMI_TTS_TIMEOUT,
    XIAOMI_TTS_VOICE,
)


class TTSError(RuntimeError):
    pass


_TONE_STYLE_MAP = {
    "温柔叮嘱": "温柔",
    "温柔": "温柔",
    "开心自信": "开心",
    "开心": "开心",
    "高兴": "开心",
    "兴奋": "兴奋",
    "悲伤": "悲伤",
    "难过": "悲伤",
    "生气": "生气",
    "愤怒": "生气",
    "害怕": "害怕",
    "惊讶": "惊讶",
    "紧张": "紧张",
    "疲惫": "疲惫",
    "狡猾": "狡猾 低声",
    "阴险": "狡猾 低声",
    "慈祥": "温柔",
    "急促": "语速变快",
    "缓慢": "语速变慢",
    "旁白": "平缓 温柔",
}


def _derive_style(tone: str | None) -> str:
    if not tone or not tone.strip():
        return ""
    tone = tone.strip()
    return _TONE_STYLE_MAP.get(tone, tone)


_STYLE_TAG_RE = re.compile(r"<\s*style[^>]*>.*?</\s*style\s*>", re.IGNORECASE | re.DOTALL)


def strip_control_tags(text: str) -> str:
    return _STYLE_TAG_RE.sub("", text or "").strip()


def _build_input(text: str, tone: str | None) -> str:
    style = _derive_style(tone)
    clean = (text or "").strip()
    if style:
        return f"<style>{style}</style>{clean}"
    return clean


def synthesize_bytes(
    text: str,
    voice: str | None = None,
    tone: str | None = None,
    speaker: str | None = None,
) -> bytes:
    if not XIAOMI_TTS_API_KEY:
        raise TTSError("XIAOMI_TTS_API_KEY not set")
    if not text or not text.strip():
        raise TTSError("empty text")

    input_text = _build_input(text, tone)
    user_hint = "请朗读以下台词，用儿童绘本故事的自然语气。"
    payload = {
        "model": XIAOMI_TTS_MODEL,
        "messages": [
            {"role": "user", "content": user_hint},
            {"role": "assistant", "content": input_text},
        ],
        "audio": {
            "format": XIAOMI_TTS_FORMAT,
            "voice": voice or XIAOMI_TTS_VOICE,
        },
    }
    headers = {
        "Authorization": f"Bearer {XIAOMI_TTS_API_KEY}",
        "api-key": XIAOMI_TTS_API_KEY,
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            f"{XIAOMI_TTS_BASE_URL.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=XIAOMI_TTS_TIMEOUT,
        )
    except requests.RequestException as e:
        raise TTSError(f"network error: {e}") from e

    if resp.status_code >= 400:
        raise TTSError(f"HTTP {resp.status_code}: {resp.text[:400]}")

    try:
        data = resp.json()
        audio_b64 = data["choices"][0]["message"]["audio"]["data"]
    except (KeyError, IndexError, ValueError) as e:
        raise TTSError(f"unexpected response shape: {str(resp.text)[:300]}") from e

    return base64.b64decode(audio_b64)


def media_type() -> str:
    fmt = XIAOMI_TTS_FORMAT.lower()
    if fmt == "mp3":
        return "audio/mpeg"
    if fmt == "wav":
        return "audio/wav"
    if fmt == "ogg":
        return "audio/ogg"
    return "application/octet-stream"
