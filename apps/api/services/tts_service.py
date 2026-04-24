import base64
import re
from concurrent.futures import ThreadPoolExecutor

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
    # 基础情绪
    "温柔叮嘱": "温柔", "温柔": "温柔", "慈祥": "温柔",
    "开心自信": "开心", "开心": "开心", "高兴": "开心",
    "兴奋": "兴奋", "激动": "兴奋",
    "悲伤": "悲伤", "难过": "悲伤", "伤心": "悲伤",
    "生气": "愤怒", "愤怒": "愤怒", "恼怒": "愤怒",
    "害怕": "恐惧", "恐惧": "恐惧", "恐慌": "恐惧",
    "惊讶": "惊讶", "震惊": "惊讶", "吃惊": "惊讶",
    "紧张": "紧张", "焦虑": "紧张", "忐忑": "紧张",
    "疲惫": "疲惫", "无力": "疲惫",
    "委屈": "委屈", "哽咽": "哽咽",
    "平静": "平静", "淡定": "平静", "冷静": "平静",
    "冷漠": "冷漠",
    # 复合情绪
    "怅然": "怅然", "欣慰": "欣慰", "无奈": "无奈",
    "愧疚": "愧疚", "释然": "释然", "厌倦": "厌倦", "动情": "动情",
    # 整体语调
    "高冷": "高冷", "活泼": "活泼", "严肃": "严肃",
    "慵懒": "慵懒", "俏皮": "俏皮", "深沉": "深沉", "干练": "干练", "凌厉": "凌厉",
    # 角色相关
    "狡猾": "狡猾 低声", "阴险": "狡猾 低声",
    "虚弱做作": "疲惫 气声", "虚弱": "疲惫 气声",
    "急促": "语速变快", "缓慢": "语速变慢",
    "旁白": "平缓 温柔", "叙述": "平缓 温柔",
    "坚定": "坚定", "自信": "自信",
    "神秘": "深沉 低声", "低语": "低声",
    "威严": "严肃 深沉", "命令": "严肃 干练",
    "撒娇": "撒娇", "可爱": "活泼 俏皮",
    "哭泣": "悲伤 哽咽", "大哭": "悲伤 嚎啕大哭",
    "笑": "开心 轻笑", "大笑": "开心 大笑", "冷笑": "冷漠 冷笑",
    "讽刺": "冷漠", "嘲笑": "冷漠 冷笑",
    "担心": "紧张 温柔", "关切": "温柔 紧张",
    "感动": "动情 温柔", "感激": "温柔 欣慰",
    "得意": "开心 自信", "骄傲": "自信",
    "尴尬": "紧张", "害羞": "温柔 紧张",
    "思考": "平静 深沉", "沉思": "平静 深沉",
}


CHARACTER_VOICE_MAP: dict[str, str] = {
    "小红帽": "冰糖",      # young female
    "妈妈": "茉莉",        # adult female
    "外婆": "茉莉",        # elder female (same voice, softer tone via style)
    "大灰狼": "白桦",      # adult male
    "猎人": "苏打",        # adult male
    "旁白": "冰糖",        # narrator = default
}
DEFAULT_CHARACTER_VOICE = "冰糖"


def _derive_style(tone: str | None) -> str:
    if not tone or not tone.strip():
        return ""
    tone = tone.strip()
    return _TONE_STYLE_MAP.get(tone, tone)


_STYLE_TAG_RE = re.compile(r"^[\(（\[].*?[\)）\]]", re.DOTALL)


def strip_control_tags(text: str) -> str:
    return _STYLE_TAG_RE.sub("", text or "").strip()


def _build_input(text: str, tone: str | None) -> str:
    style = _derive_style(tone)
    clean = (text or "").strip()
    if style:
        return f"({style}){clean}"
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

    # Resolve voice: explicit > character map > config default
    resolved_voice = voice
    if resolved_voice is None and speaker:
        resolved_voice = CHARACTER_VOICE_MAP.get(speaker, DEFAULT_CHARACTER_VOICE)
    if resolved_voice is None:
        resolved_voice = XIAOMI_TTS_VOICE

    input_text = _build_input(text, tone)
    style_label = _derive_style(tone) or "温柔"
    user_hint = f"请用{style_label}的语气朗读以下台词，语速适中，适合给5岁儿童听的绘本故事。"
    payload = {
        "model": XIAOMI_TTS_MODEL,
        "messages": [
            {"role": "user", "content": user_hint},
            {"role": "assistant", "content": input_text},
        ],
        "audio": {
            "format": XIAOMI_TTS_FORMAT,
            "voice": resolved_voice,
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


def synthesize_batch(items: list[dict]) -> list[bytes]:
    """Synthesize multiple TTS items in parallel.

    items: [{"text": str, "voice": str|None, "tone": str|None, "speaker": str|None}]
    Returns a list of audio bytes in the same order as input items.
    """
    def _do(item: dict) -> bytes:
        return synthesize_bytes(
            text=item.get("text", ""),
            voice=item.get("voice"),
            tone=item.get("tone"),
            speaker=item.get("speaker"),
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_do, item) for item in items]
        return [f.result() for f in futures]


def media_type() -> str:
    fmt = XIAOMI_TTS_FORMAT.lower()
    if fmt == "mp3":
        return "audio/mpeg"
    if fmt == "wav":
        return "audio/wav"
    if fmt == "ogg":
        return "audio/ogg"
    return "application/octet-stream"
