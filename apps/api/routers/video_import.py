from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from ..db import user_by_token
from ..models import StoryCard, VideoStoryCreateRequest
from ..services.video_import_service import submit_video_story
from ..story_registry import story_exists

router = APIRouter()


@router.post("/stories/from-video", response_model=StoryCard)
def create_story_from_video(req: VideoStoryCreateRequest, authorization: Optional[str] = Header(default=None)) -> StoryCard:
    user = _require_user(authorization)
    try:
        record = submit_video_story(req.url, title=req.title, owner_user_id=user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=424, detail=str(exc))
    return _record_to_card(record)


def _record_to_card(record: dict) -> StoryCard:
    status = record.get("status") or "generating"
    available = status == "ready" and story_exists(record.get("id"))
    return StoryCard(
        id=record["id"],
        title=record.get("title") or "视频导入故事",
        summary=record.get("summary") or "",
        cover_url=record.get("cover_url") or "",
        scene_count=int(record.get("scene_count") or 0),
        available=available,
        status=status if status in {"ready", "generating", "failed"} else "generating",
        is_custom=True,
        error_message=record.get("error_message"),
        progress=int(record.get("progress") or 0),
        progress_label=record.get("progress_label") or "",
    )


def _extract_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


def _require_user(authorization: Optional[str]) -> dict:
    user = user_by_token(_extract_token(authorization))
    if not user:
        raise HTTPException(status_code=401, detail="请先登录后再导入视频故事。")
    return user
