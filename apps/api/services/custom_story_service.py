import shutil
import sys
from argparse import Namespace
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

from ..asset_resolver import url_for
from ..config import (
    CUSTOM_STORIES_ROOT,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    PROJECT_ROOT,
    SEEDREAM_API_KEY,
    SEEDREAM_BASE_URL,
    SEEDREAM_MODEL,
    SEEDREAM_PROVIDER,
    SEEDREAM_SIZE,
)
from ..scene_loader import clear_story_cache, load_story
from ..story_registry import (
    create_custom_story_record,
    custom_story_workspace,
    get_custom_story_record,
    story_root,
    update_custom_story_record,
)
from .placement_service import clear_layout_cache
from .suggestion_service import ensure_scene_questions_for_story

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.story.story_scene_splitter import DEFAULT_BASE_URL
from scripts.workflow.story_asset_workflow import DEFAULT_MAX_WORKERS, DEFAULT_QWEN_MODEL, run_workflow

def _new_executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix="custom-story")


_EXECUTOR = _new_executor()
_FUTURES: dict[str, Future] = {}
_FUTURES_LOCK = Lock()


def submit_custom_story(text: str, title: str = "", owner_user_id: str | None = None) -> dict:
    clean = (text or "").strip()
    if not clean:
        raise ValueError("请先输入故事内容。")
    if not SEEDREAM_API_KEY:
        raise RuntimeError("服务器未配置 SEEDREAM_API_KEY，暂时不能生成自定义故事。")
    if not LLM_API_KEY:
        raise RuntimeError("服务器未配置 LLM_API_KEY（或 DASHSCOPE_API_KEY），暂时不能生成自定义故事。")

    record = create_custom_story_record(clean, title=title, owner_user_id=owner_user_id)
    schedule_custom_story_build(record["id"], clean)
    return record


def schedule_custom_story_build(story_id: str, text: str, *, resume: bool = False) -> None:
    global _EXECUTOR
    clean = (text or "").strip()
    if not clean:
        raise ValueError("请先输入故事内容。")
    # The module-level thread pool can be left shut down after a dev-server (--reload)
    # restart — submit() then raises "cannot schedule new futures after …". Recreate
    # the pool once and retry; if it still fails the interpreter is genuinely tearing
    # down, so mark the record failed (don't leave it stuck "generating") and surface
    # a clear, retryable message instead of a 500.
    try:
        future = _EXECUTOR.submit(_build_story_assets, story_id, clean, resume)
    except RuntimeError:
        _EXECUTOR = _new_executor()
        try:
            future = _EXECUTOR.submit(_build_story_assets, story_id, clean, resume)
        except RuntimeError as exc:
            update_custom_story_record(
                story_id,
                status="failed",
                error_message="服务正在重启，请稍后再点重试。",
                progress=0,
                progress_label="",
            )
            raise RuntimeError("服务正在重启，请稍后再点重试。") from exc
    with _FUTURES_LOCK:
        _FUTURES[story_id] = future
    future.add_done_callback(lambda _: _forget_future(story_id))


def retry_custom_story(story_id: str) -> dict:
    """Resume a failed custom-story build using its stored original text.

    Re-runs the asset workflow in *resume* mode: scenes / global assets / per-scene
    assets that already exist on disk are skipped, so generation continues from
    where it left off instead of starting over.
    """
    record = get_custom_story_record(story_id)
    if not record:
        raise ValueError("故事不存在。")
    text = (record.get("input_text") or "").strip()
    if not text:
        raise ValueError("缺少原始故事文本，无法续跑，请重新创建这个故事。")
    if not SEEDREAM_API_KEY:
        raise RuntimeError("服务器未配置 SEEDREAM_API_KEY，暂时不能生成自定义故事。")
    if not LLM_API_KEY:
        raise RuntimeError("服务器未配置 LLM_API_KEY（或 DASHSCOPE_API_KEY），暂时不能生成自定义故事。")

    with _FUTURES_LOCK:
        active = _FUTURES.get(story_id)
        if active is not None and not active.done():
            raise ValueError("该故事正在生成中，请稍候。")

    update_custom_story_record(
        story_id,
        status="generating",
        error_message=None,
        progress=max(int(record.get("progress") or 0), 5),
        progress_label="继续生成中",
    )
    schedule_custom_story_build(story_id, text, resume=True)
    return get_custom_story_record(story_id) or record


def _set_progress(story_id: str, progress: int, label: str) -> None:
    update_custom_story_record(story_id, progress=progress, progress_label=label)


def _build_story_assets(story_id: str, text: str, resume: bool = False) -> None:
    workspace = custom_story_workspace(story_id)
    output_root = story_root(story_id)
    if resume:
        # Resume: keep whatever was already generated and only fill the gaps.
        # Reuse the split scenes / global assets when present so the workflow jumps
        # straight to the per-scene assets it hasn't produced yet (it skips files
        # that already exist on disk).
        scenes_done = (output_root / "story_scenes.json").exists()
        global_done = (output_root / "global" / "manifest.json").exists()
    else:
        if workspace.exists():
            shutil.rmtree(workspace)
        scenes_done = False
        global_done = False
    CUSTOM_STORIES_ROOT.mkdir(parents=True, exist_ok=True)

    try:
        _set_progress(story_id, 5, "继续生成中" if resume else "拆分场景中")
        args = Namespace(
            text=text,
            input_file=None,
            output_root=str(output_root),
            scenes_json=str(output_root / "story_scenes.json"),
            use_existing_scenes=scenes_done,
            use_existing_global=global_done,
            interactive_only=False,
            narrative_only=False,
            # workflow 里的 "dashscope_api_key" 字段名是历史命名，实际是 chat LLM 的 key —
            # 这里传 LLM_API_KEY（默认走 mikaovo.ai）；ASR 在 qwen_service 里另外用 DASHSCOPE_API_KEY。
            dashscope_api_key=LLM_API_KEY,
            ark_api_key=SEEDREAM_API_KEY,
            qwen_model=LLM_MODEL,
            seedream_model=SEEDREAM_MODEL,
            seedream_base_url=SEEDREAM_BASE_URL,
            base_url=LLM_BASE_URL,
            provider=SEEDREAM_PROVIDER,
            temperature=0.2,
            # Moderate per-call timeout: long enough for a slow-but-healthy gateway
            # response, short enough that a stalled call fails and *retries* (see
            # post_with_retry) instead of appearing frozen for many minutes. The
            # substantive resilience comes from the 2x retry on timeouts + 429/5xx.
            timeout=360,
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
