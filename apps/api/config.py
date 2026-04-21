import os
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
APPS_DIR = API_DIR.parent
PROJECT_ROOT = APPS_DIR.parent

SCENES_DIR = PROJECT_ROOT / "scenes"
STORY_JSON = SCENES_DIR / "story_scenes.json"

FRONTEND_DIR = APPS_DIR / "web"
OUTPUTS_ROOT = PROJECT_ROOT / "outputs" / "webdemo"
OUTPUTS_ROOT.mkdir(parents=True, exist_ok=True)
CUSTOM_STORIES_ROOT = OUTPUTS_ROOT / "stories"
CUSTOM_STORIES_ROOT.mkdir(parents=True, exist_ok=True)

ARK_API_KEY = os.getenv("ARK_API_KEY", "")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

SEEDREAM_MODEL = os.getenv("SEEDREAM_MODEL", "doubao-seedream-5-0-lite-260128")
SEEDREAM_PROVIDER = os.getenv("SEEDREAM_PROVIDER", "ark")
SEEDREAM_SIZE = os.getenv("SEEDREAM_SIZE", "1920x1920")
SEEDREAM_TIMEOUT = int(os.getenv("SEEDREAM_TIMEOUT", "180"))

# TTS: Xiaomi MiMo v2 TTS (OpenAI-compatible chat/completions endpoint)
XIAOMI_TTS_API_KEY = os.getenv("XIAOMI_TTS_API_KEY", "")
XIAOMI_TTS_BASE_URL = os.getenv("XIAOMI_TTS_BASE_URL", "https://api.xiaomimimo.com/v1")
XIAOMI_TTS_MODEL = os.getenv("XIAOMI_TTS_MODEL", "mimo-v2-tts")
XIAOMI_TTS_VOICE = os.getenv("XIAOMI_TTS_VOICE", "mimo_default")
XIAOMI_TTS_FORMAT = os.getenv("XIAOMI_TTS_FORMAT", "wav")
XIAOMI_TTS_TIMEOUT = int(os.getenv("XIAOMI_TTS_TIMEOUT", "60"))

DEFAULT_TTS_VOICE = os.getenv("TTS_VOICE", XIAOMI_TTS_VOICE)
