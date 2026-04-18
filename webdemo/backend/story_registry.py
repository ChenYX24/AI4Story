import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import CUSTOM_STORIES_ROOT, SCENES_DIR

DEFAULT_STORY_ID = "little_red_riding_hood"
REGISTRY_PATH = CUSTOM_STORIES_ROOT / "registry.json"

_REGISTRY_LOCK = threading.RLock()


def is_default_story(story_id: str | None) -> bool:
    return not story_id or story_id == DEFAULT_STORY_ID


def story_root(story_id: str | None) -> Path:
    if is_default_story(story_id):
        return SCENES_DIR
    return CUSTOM_STORIES_ROOT / str(story_id) / "scenes"


def story_json_path(story_id: str | None) -> Path:
    return story_root(story_id) / "story_scenes.json"


def story_exists(story_id: str | None) -> bool:
    return story_json_path(story_id).exists()


def custom_story_workspace(story_id: str) -> Path:
    return CUSTOM_STORIES_ROOT / story_id


def load_registry() -> dict[str, dict[str, Any]]:
    with _REGISTRY_LOCK:
        if not REGISTRY_PATH.exists():
            return {}
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(data: dict[str, dict[str, Any]]) -> None:
    with _REGISTRY_LOCK:
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        REGISTRY_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def list_custom_story_records() -> list[dict[str, Any]]:
    data = load_registry()
    return sorted(
        data.values(),
        key=lambda item: item.get("created_at", ""),
        reverse=True,
    )


def get_custom_story_record(story_id: str) -> dict[str, Any] | None:
    return load_registry().get(story_id)


def create_custom_story_record(text: str) -> dict[str, Any]:
    clean = " ".join((text or "").split())
    story_id = f"custom-{uuid.uuid4().hex[:10]}"
    now = _utc_now()
    record = {
        "id": story_id,
        "title": _derive_title(clean),
        "summary": _excerpt(clean, 88),
        "input_text": clean,
        "scene_count": 0,
        "cover_url": "",
        "status": "generating",
        "error_message": None,
        "progress": 0,
        "progress_label": "准备中",
        "created_at": now,
        "updated_at": now,
    }
    update_custom_story_record(story_id, **record)
    return record


def delete_custom_story_record(story_id: str) -> bool:
    with _REGISTRY_LOCK:
        data = load_registry()
        if story_id not in data:
            return False
        del data[story_id]
        save_registry(data)
    workspace = custom_story_workspace(story_id)
    if workspace.exists():
        import shutil
        shutil.rmtree(workspace, ignore_errors=True)
    return True


def update_custom_story_record(story_id: str, **updates: Any) -> dict[str, Any]:
    with _REGISTRY_LOCK:
        data = load_registry()
        current = data.get(story_id, {"id": story_id})
        current.update(updates)
        current["updated_at"] = _utc_now()
        data[story_id] = current
        save_registry(data)
        return current


def mark_interrupted_generations_failed() -> None:
    data = load_registry()
    changed = False
    for record in data.values():
        if record.get("status") != "generating":
            continue
        record["status"] = "failed"
        record["error_message"] = "生成任务已中断，请重新创建这个故事。"
        record["updated_at"] = _utc_now()
        changed = True
    if changed:
        save_registry(data)


def _derive_title(text: str) -> str:
    compact = "".join(text.split())
    if not compact:
        return "我的自定义故事"
    return compact[:16] + ("..." if len(compact) > 16 else "")


def _excerpt(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


mark_interrupted_generations_failed()
