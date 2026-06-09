import os
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
APPS_DIR = API_DIR.parent
PROJECT_ROOT = APPS_DIR.parent

SCENES_DIR = PROJECT_ROOT / "scenes"
STORY_JSON = SCENES_DIR / "story_scenes.json"

# 前端：v2 是 Vite 工程，build 产物在 apps/web/dist/；
# main.py 会优先用 dist/index.html，否则退回 web-legacy（原生 JS 版）
FRONTEND_DIR = APPS_DIR / "web"  # 保留兼容；main.py 内有更细判断
OUTPUTS_ROOT = PROJECT_ROOT / "outputs" / "webdemo"
OUTPUTS_ROOT.mkdir(parents=True, exist_ok=True)
CUSTOM_STORIES_ROOT = OUTPUTS_ROOT / "stories"
CUSTOM_STORIES_ROOT.mkdir(parents=True, exist_ok=True)

ARK_API_KEY = os.getenv("ARK_API_KEY", "")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
QWEN_ASR_MODEL = os.getenv("QWEN_ASR_MODEL", "qwen3-asr-flash-2026-02-10")


def _normalize_openai_base_url(raw: str | None, default: str) -> str:
    base = (raw or default).strip().rstrip("/")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    if base.endswith("/images/generations"):
        base = base[: -len("/images/generations")]
    tail = base.rsplit("/", 1)[-1]
    if tail.startswith("v") and tail[1:].replace(".", "").isdigit():
        return base
    return f"{base}/v1"


# Chat / text LLM. DASHSCOPE_API_KEY is kept for ASR only.
LLM_BASE_URL = _normalize_openai_base_url(
    os.getenv("LLM_BASE_URL") or os.getenv("API_ENDPOINT"),
    "https://api.mikaovo.ai",
)
LLM_MODEL = os.getenv("LLM_MODEL", "grok-4.3")
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip() or DASHSCOPE_API_KEY

SEEDREAM_MODEL = os.getenv("SEEDREAM_MODEL", "doubao-seedream-5-0-lite-260128")
SEEDREAM_API_KEY = (
    os.getenv("SEEDREAM_API_KEY", "").strip()
    or os.getenv("ARK_API_KEY", "").strip()
    or LLM_API_KEY
)
SEEDREAM_BASE_URL = _normalize_openai_base_url(
    os.getenv("SEEDREAM_BASE_URL") or os.getenv("API_ENDPOINT") or os.getenv("LLM_BASE_URL"),
    "https://api.mikaovo.ai",
)
SEEDREAM_PROVIDER = os.getenv("SEEDREAM_PROVIDER") or (
    "ark"
    if (
        os.getenv("ARK_API_KEY")
        and not os.getenv("SEEDREAM_API_KEY")
        and not os.getenv("API_ENDPOINT")
        and not os.getenv("SEEDREAM_BASE_URL")
    )
    else "openai"
)
SEEDREAM_SIZE = os.getenv("SEEDREAM_SIZE", "1920x1920")
SEEDREAM_TIMEOUT = int(os.getenv("SEEDREAM_TIMEOUT", "180"))

# TTS: Xiaomi MiMo v2 TTS (OpenAI-compatible chat/completions endpoint)
XIAOMI_TTS_API_KEY = os.getenv("XIAOMI_TTS_API_KEY", "")
XIAOMI_TTS_BASE_URL = os.getenv("XIAOMI_TTS_BASE_URL", "https://api.xiaomimimo.com/v1")
XIAOMI_TTS_MODEL = os.getenv("XIAOMI_TTS_MODEL", "mimo-v2.5-tts")
XIAOMI_TTS_VOICE = os.getenv("XIAOMI_TTS_VOICE", "冰糖")
XIAOMI_TTS_FORMAT = os.getenv("XIAOMI_TTS_FORMAT", "mp3")
XIAOMI_TTS_TIMEOUT = int(os.getenv("XIAOMI_TTS_TIMEOUT", "60"))

DEFAULT_TTS_VOICE = os.getenv("TTS_VOICE", XIAOMI_TTS_VOICE)
