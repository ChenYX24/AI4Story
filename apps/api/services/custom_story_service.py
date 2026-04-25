import shutil
import sys
from argparse import Namespace
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

from ..asset_resolver import url_for
from ..config import (
    ARK_API_KEY,
    CUSTOM_STORIES_ROOT,
    DASHSCOPE_API_KEY,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    PROJECT_ROOT,
    SEEDREAM_MODEL,
    SEEDREAM_PROVIDER,
    SEEDREAM_SIZE,
)
from ..scene_loader import clear_story_cache, load_story
from ..story_registry import (
    create_custom_story_record,
    custom_story_workspace,
    story_root,
    update_custom_story_record,
)
from .placement_service import clear_layout_cache
from .suggestion_service import ensure_scene_questions_for_story

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.story.story_scene_splitter import DEFAULT_BASE_URL
from scripts.workflow.story_asset_workflow import DEFAULT_MAX_WORKERS, DEFAULT_QWEN_MODEL, run_workflow

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="custom-story")
_FUTURES: dict[str, Future] = {}
_FUTURES_LOCK = Lock()


def submit_custom_story(text: str, title: str = "", owner_user_id: str | None = None) -> dict:
    clean = (text or "").strip()
    if not clean:
        raise ValueError("请先输入故事内容。")
    if not ARK_API_KEY:
        raise RuntimeError("服务器未配置 ARK_API_KEY，暂时不能生成自定义故事。")
    if not LLM_API_KEY:
        raise RuntimeError("服务器未配置 LLM_API_KEY（或 DASHSCOPE_API_KEY），暂时不能生成自定义故事。")

    record = create_custom_story_record(clean, title=title, owner_user_id=owner_user_id)
    schedule_custom_story_build(record["id"], clean)
    return record


def schedule_custom_story_build(story_id: str, text: str) -> None:
    clean = (text or "").strip()
    if not clean:
        raise ValueError("请先输入故事内容。")
    future = _EXECUTOR.submit(_build_story_assets, story_id, clean)
    with _FUTURES_LOCK:
        _FUTURES[story_id] = future
    future.add_done_callback(lambda _: _forget_future(story_id))


def _set_progress(story_id: str, progress: int, label: str) -> None:
    update_custom_story_record(story_id, progress=progress, progress_label=label)


def _build_story_assets(story_id: str, text: str) -> None:
    workspace = custom_story_workspace(story_id)
    output_root = story_root(story_id)
    if workspace.exists():
        shutil.rmtree(workspace)
    CUSTOM_STORIES_ROOT.mkdir(parents=True, exist_ok=True)

    try:
        _set_progress(story_id, 5, "拆分场景中")
        args = Namespace(
            text=text,
            input_file=None,
            output_root=str(output_root),
            scenes_json=str(output_root / "story_scenes.json"),
            use_existing_scenes=False,
            use_existing_global=False,
            interactive_only=False,
            narrative_only=False,
            # workflow 里的 "dashscope_api_key" 字段名是历史命名，实际是 chat LLM 的 key —
            # 这里传 LLM_API_KEY（默认走 mikaovo.ai）；ASR 在 qwen_service 里另外用 DASHSCOPE_API_KEY。
            dashscope_api_key=LLM_API_KEY,
            ark_api_key=ARK_API_KEY,
            qwen_model=LLM_MODEL,
            seedream_model=SEEDREAM_MODEL,
            base_url=LLM_BASE_URL,
            provider=SEEDREAM_PROVIDER,
            temperature=0.2,
            timeout=300,
            asset_size=SEEDREAM_SIZE,
            background_size=SEEDREAM_SIZE,
            target_total_scenes=0,
            max_narrative_scenes=0,
            max_workers=64,
            # 单个场景内有 background / characters / objects / comic 四类任务并发，
            # 故 asset_workers 至少给到 6，让 comic 不会成为单场景串行尾巴。
            asset_workers=max(6, min(8, DEFAULT_MAX_WORKERS)),
            no_progress=True,
            progress_callback=lambda p, label: _set_progress(story_id, p, label),
        )
        run_workflow(args)
        _set_progress(story_id, 92, "整理资源中")
        clear_story_cache(story_id)
        clear_layout_cache(story_id)
        # 预生成每幕聊天建议问题，保证前端第一次打开聊天气泡即有数据
        _set_progress(story_id, 95, "生成聊天建议")
        try:
            ensure_scene_questions_for_story(story_id)
        except Exception as e:
            print(f"[custom_story] pre-gen suggestions failed: {e}")
        clear_story_cache(story_id)
        story = load_story(story_id)
        scenes = story.get("scenes", [])
        first_narrative_idx = next(
            (
                int(scene["scene_index"])
                for scene in scenes
                if scene.get("scene_type") == "叙事场景"
            ),
            int(scenes[0]["scene_index"]) if scenes else 1,
        )
        update_custom_story_record(
            story_id,
            status="ready",
            summary=story.get("story_summary", ""),
            scene_count=len(scenes),
            cover_url=url_for(first_narrative_idx, "comic", story_id=story_id) if scenes else "",
            error_message=None,
            progress=100,
            progress_label="生成完成",
        )
    except Exception as exc:
        clear_story_cache(story_id)
        clear_layout_cache(story_id)
        update_custom_story_record(
            story_id,
            status="failed",
            error_message=str(exc),
            progress=0,
            progress_label="",
        )


def _forget_future(story_id: str) -> None:
    with _FUTURES_LOCK:
        _FUTURES.pop(story_id, None)
