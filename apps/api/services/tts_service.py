import base64
import hashlib
import os
import re
import threading
from collections import Counter
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


# Xiaomi MiMo TTS 实际接受的 voice 名（来自上游报错信息）。
_ALLOWED_VOICES = {
    "mimo_default",
    "冰糖", "茉莉", "苏打", "白桦",
    "Mia", "Chloe", "Milo", "Dean",
}
# 历史调用方 / 旧代码可能仍传 default_zh / default_en —— 在这里翻译成真实 voice。
_LEGACY_VOICE_MAP = {
    "default_zh": "mimo_default",
    "default_en": "mimo_default",
}

# 旁白固定使用一个偏中性的音色，所有故事共用，一眼能识别"这是叙述"。
_NARRATOR_VOICE = "mimo_default"
_NARRATOR_ALIASES = {
    "旁白", "叙述", "叙述者", "讲述", "讲述者", "解说",
    "narrator", "narration",
}

# 角色音色池：旁白单独占用 mimo_default，其余角色按名字哈希分配，
# 中文名走中文池，英文/拉丁名走英文池，从而：
#   - 同一角色名永远拿到同一个音色（跨请求/跨故事）
#   - 同一个故事里不同角色尽量落在不同音色上（5/4 个槽位足够大多数儿童绘本）
#   - 不依赖任何故事/角色硬编码
_ZH_CHARACTER_VOICES: list[str] = ["冰糖", "茉莉", "苏打", "白桦"]
_EN_CHARACTER_VOICES: list[str] = ["Mia", "Chloe", "Milo", "Dean"]

# 默认 voice -> 性别 映射（小米 MiMo 没有公开声纹性别，取常见命名/听感作默认）。
# 部署侧可通过 XIAOMI_TTS_VOICE_GENDERS=冰糖:female,白桦:male,... 覆盖。
_DEFAULT_VOICE_GENDERS: dict[str, str] = {
    "mimo_default": "neutral",
    "冰糖": "female",
    "茉莉": "female",
    "苏打": "male",
    "白桦": "male",
    "Mia": "female",
    "Chloe": "female",
    "Milo": "male",
    "Dean": "male",
}


def _load_voice_gender_overrides() -> dict[str, str]:
    raw = os.getenv("XIAOMI_TTS_VOICE_GENDERS", "").strip()
    if not raw:
        return {}
    overrides: dict[str, str] = {}
    for chunk in raw.split(","):
        if ":" not in chunk:
            continue
        name, gender = chunk.split(":", 1)
        name = name.strip()
        gender = gender.strip().lower()
        if name and gender in {"male", "female", "neutral"}:
            overrides[name] = gender
    return overrides


_VOICE_GENDERS: dict[str, str] = {**_DEFAULT_VOICE_GENDERS, **_load_voice_gender_overrides()}


def _voice_pool_for(language_pool: list[str], gender: str | None) -> list[str]:
    """从语言池里筛出与 gender 匹配的子集；性别未知/匹配为空时退化到原池。"""
    g = (gender or "").strip().lower()
    if g not in {"male", "female"}:
        return language_pool
    matched = [v for v in language_pool if _VOICE_GENDERS.get(v, "neutral") == g]
    return matched or language_pool


DEFAULT_CHARACTER_VOICE = _NARRATOR_VOICE


def _is_narrator(name: str) -> bool:
    s = (name or "").strip()
    if not s:
        return True
    return s in _NARRATOR_ALIASES or s.lower() in _NARRATOR_ALIASES


def _has_chinese(name: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in name)


# 进程内的"故事-说话人 -> voice"分配缓存。同一 story_id 下，新出现的说话人
# 优先选当前用得最少的音色，从而让一个故事里的不同角色尽量分到不同声音；
# 旧说话人复用已分配的音色，保证同一段对话音色稳定。
_VOICE_CACHE_LOCK = threading.Lock()
_VOICE_CACHE: dict[tuple[str, str], str] = {}
_VOICE_USAGE: dict[str, Counter] = {}


def voice_for_speaker(
    speaker: str | None,
    story_id: str | None = None,
    gender: str | None = None,
) -> str:
    """speaker -> voice，按 (story_id, speaker, gender) 稳定分配。

    - 旁白类名字固定 _NARRATOR_VOICE。
    - 其余名字先按语言（中/英）选语言池，再按 gender（male/female）裁剪到子池，
      然后在子池内挑"当前 story 用得最少的音色"；并列时用 md5 哈希决定，保证同一
      (story_id, speaker, gender) 永远落到同一个音色。
    - 性别未知或子池为空时，回退到完整语言池。
    """
    s = (speaker or "").strip()
    if _is_narrator(s):
        return _NARRATOR_VOICE
    language_pool = _EN_CHARACTER_VOICES if not _has_chinese(s) else _ZH_CHARACTER_VOICES
    pool = _voice_pool_for(language_pool, gender)
    sid = (story_id or "").strip() or "_default"
    g_label = (gender or "").strip().lower() or "?"
    key = (sid, f"{g_label}|{s}")
    with _VOICE_CACHE_LOCK:
        cached = _VOICE_CACHE.get(key)
        if cached and cached in pool:
            return cached
        usage = _VOICE_USAGE.setdefault(sid, Counter())
        digest = hashlib.md5(f"{sid}|{g_label}|{s}".encode("utf-8")).digest()
        seed = int.from_bytes(digest[:4], "big")
        ranked = sorted(
            range(len(pool)),
            key=lambda i: (usage[pool[i]], (seed + i) % len(pool)),
        )
        chosen = pool[ranked[0]]
        _VOICE_CACHE[key] = chosen
        usage[chosen] += 1
        return chosen


def reset_voice_cache(story_id: str | None = None) -> None:
    """测试 / 维护用：清空整张缓存或某个故事的缓存。"""
    with _VOICE_CACHE_LOCK:
        if story_id is None:
            _VOICE_CACHE.clear()
            _VOICE_USAGE.clear()
            return
        sid = (story_id or "").strip() or "_default"
        _VOICE_USAGE.pop(sid, None)
        for k in list(_VOICE_CACHE.keys()):
            if k[0] == sid:
                _VOICE_CACHE.pop(k, None)


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
    story_id: str | None = None,
    speaker_gender: str | None = None,
) -> bytes:
    if not XIAOMI_TTS_API_KEY:
        raise TTSError("XIAOMI_TTS_API_KEY not set")
    if not text or not text.strip():
        raise TTSError("empty text")

    # Resolve voice: 显式 voice 优先 -> 按 (story_id, speaker, gender) 分配 -> 配置默认
    resolved_voice = (voice or "").strip() or None
    if resolved_voice is None:
        resolved_voice = voice_for_speaker(speaker, story_id=story_id, gender=speaker_gender)
    resolved_voice = _LEGACY_VOICE_MAP.get(resolved_voice, resolved_voice)
    if resolved_voice not in _ALLOWED_VOICES:
        # 配置层默认（XIAOMI_TTS_VOICE）也走一次合法化，如果还非法就回落 narrator
        candidate = _LEGACY_VOICE_MAP.get(XIAOMI_TTS_VOICE, XIAOMI_TTS_VOICE)
        resolved_voice = candidate if candidate in _ALLOWED_VOICES else _NARRATOR_VOICE

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


def synthesize_batch(items: list[dict], story_id: str | None = None) -> list[bytes]:
    """Synthesize multiple TTS items in parallel.

    items: [{"text": str, "voice": str|None, "tone": str|None, "speaker": str|None,
             "speaker_gender": str|None, "story_id": str|None}]
    Returns a list of audio bytes in the same order as input items.

    在并发触发前，先把所有未指定 voice 的 (story_id, speaker, gender) 串行预分配一遍，
    避免多线程同时撞同一把锁、又或并列时拿到不同 voice。
    """
    # 预分配
    for item in items:
        if item.get("voice"):
            continue
        sp = item.get("speaker")
        sid = item.get("story_id") or story_id
        gender = item.get("speaker_gender")
        voice_for_speaker(sp, story_id=sid, gender=gender)

    def _do(item: dict) -> bytes:
        return synthesize_bytes(
            text=item.get("text", ""),
            voice=item.get("voice"),
            tone=item.get("tone"),
            speaker=item.get("speaker"),
            story_id=item.get("story_id") or story_id,
            speaker_gender=item.get("speaker_gender"),
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
