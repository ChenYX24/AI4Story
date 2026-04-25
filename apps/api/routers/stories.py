from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from ..asset_resolver import url_for
from ..db import user_by_token
from .. import db
from ..models import CustomStoryCreateRequest, StoriesResponse, StoryCard
from ..scene_loader import load_story
from ..services.custom_story_service import submit_custom_story
from ..story_registry import delete_custom_story_record, list_custom_story_records, story_exists, story_root, update_custom_story_record


def _sync_custom_story_to_db(record: dict, *, public: bool) -> None:
    """把 registry 里的一条原创故事记录同步到 DB stories 表。
    user_story_bookmarks 通过 FK 引用 stories.id；要让别人 bookmark 必须先有 DB 行。
    """
    if not record or not record.get("id"):
        return
    db.upsert_story({
        "id": record["id"],
        "title": record.get("title") or "我的自定义故事",
        "summary": record.get("summary") or "",
        "cover_url": record.get("cover_url") or "",
        "scene_count": int(record.get("scene_count") or 0),
        "status": record.get("status") or "ready",
        "error_message": record.get("error_message"),
        "progress": int(record.get("progress") or 100),
        "progress_label": record.get("progress_label") or "",
        "is_official": False,
        "public": public,
        "owner_user_id": record.get("owner_user_id"),
        "raw_meta": {},
        "likes": 0,
        "input_text": record.get("input_text") or "",
    })

router = APIRouter()


@router.get("/stories", response_model=StoriesResponse)
def stories(authorization: Optional[str] = Header(default=None)) -> StoriesResponse:
    default_story = load_story()
    user = _user_from_auth(authorization)
    custom_cards = _build_custom_story_cards(user["id"] if user else None)
    bookmarked_cards: list[StoryCard] = []
    if user:
        for row in db.list_bookmarked_stories(user["id"]):
            bookmarked_cards.append(_db_row_to_card(row, bookmarked=True))
    return StoriesResponse(stories=[_build_default_story_card(default_story), *custom_cards, *bookmarked_cards])


@router.post("/stories/custom", response_model=StoryCard)
def create_custom_story(req: CustomStoryCreateRequest, authorization: Optional[str] = Header(default=None)) -> StoryCard:
    user = _require_user(authorization)
    try:
        record = submit_custom_story(req.text, title=req.title, owner_user_id=user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=424, detail=str(exc))
    return _custom_record_to_card(record)


@router.get("/stories/custom/{story_id}", response_model=StoryCard)
def get_custom_story(story_id: str, authorization: Optional[str] = Header(default=None)) -> StoryCard:
    """Single-record polling endpoint for the custom-story progress UI.

    Public read: returns the StoryCard for the given id. The custom-story
    pipeline writes status / progress / error_message into the registry, so
    the frontend can poll this URL to get fresh state without needing the
    full /api/stories list (which is filtered by owner).
    """
    record = next((r for r in list_custom_story_records() if r.get("id") == story_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="故事不存在。")
    user = _user_from_auth(authorization)
    owner = record.get("owner_user_id")
    # Private records — only the owner can see status. Public records (no owner)
    # are visible to anyone.
    if owner and (not user or user.get("id") != owner):
        raise HTTPException(status_code=404, detail="故事不存在。")
    return _custom_record_to_card(record)


@router.delete("/stories/custom/{story_id}", status_code=204)
def delete_custom_story(story_id: str, authorization: Optional[str] = Header(default=None)) -> None:
    user = _require_user(authorization)
    record = next((r for r in list_custom_story_records() if r.get("id") == story_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="故事不存在。")
    if record.get("owner_user_id") and record.get("owner_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="只能删除自己的故事。")
    if not delete_custom_story_record(story_id):
        raise HTTPException(status_code=404, detail="故事不存在。")


@router.patch("/stories/custom/{story_id}", response_model=StoryCard)
def patch_custom_story(story_id: str, body: dict, authorization: Optional[str] = Header(default=None)) -> StoryCard:
    user = _require_user(authorization)
    existing = next((r for r in list_custom_story_records() if r.get("id") == story_id), None)
    if not existing:
        raise HTTPException(status_code=404, detail="故事不存在。")
    if existing.get("owner_user_id") and existing.get("owner_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="只能编辑自己的故事。")

    updates: dict = {}
    if "title" in body:
        title = (body.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="标题不能为空。")
        updates["title"] = title
    if "public" in body:
        # 必须等故事生成完成才能分享
        if (existing.get("status") or "") != "ready":
            raise HTTPException(status_code=400, detail="故事还没生成完，暂时不能分享。")
        updates["public"] = bool(body.get("public"))

    if not updates:
        raise HTTPException(status_code=400, detail="没有需要更新的字段。")

    record = update_custom_story_record(story_id, **updates)
    # 如果改了 public 状态，同步到 DB stories 表（bookmark 走 FK 必须有这一行）
    if "public" in updates:
        _sync_custom_story_to_db(record, public=bool(updates["public"]))
    return _custom_record_to_card(record)


@router.post("/stories/{story_id}/bookmark", status_code=204)
def bookmark_story(story_id: str, authorization: Optional[str] = Header(default=None)) -> None:
    """把别人 share 出来的公开故事加入到自己的"已收藏"。重复加 idempotent。"""
    user = _require_user(authorization)
    if not db.add_story_bookmark(user["id"], story_id):
        raise HTTPException(status_code=404, detail="故事不可收藏（不公开 / 是自己的 / 已被删除）。")


@router.delete("/stories/{story_id}/bookmark", status_code=204)
def unbookmark_story(story_id: str, authorization: Optional[str] = Header(default=None)) -> None:
    user = _require_user(authorization)
    db.remove_story_bookmark(user["id"], story_id)


def _build_default_story_card(story: dict) -> StoryCard:
    scenes = story.get("scenes", [])
    first_narrative_idx = next(
        (
            int(scene["scene_index"])
            for scene in scenes
            if scene.get("scene_type") == "叙事场景"
        ),
        int(scenes[0]["scene_index"]) if scenes else 1,
    )
    return StoryCard(
        id="little_red_riding_hood",
        title="小红帽",
        summary=story.get("story_summary", ""),
        cover_url=url_for(first_narrative_idx, "comic") if scenes else "",
        scene_count=len(scenes),
        available=True,
        status="ready",
    )


def _build_custom_story_cards(user_id: str | None) -> list[StoryCard]:
    if not user_id:
        return []
    return [
        _custom_record_to_card(record)
        for record in list_custom_story_records()
        if record.get("owner_user_id") == user_id
    ]


def _custom_cover_url(record: dict) -> str:
    story_id = record.get("id") or ""
    cover = str(record.get("cover_url") or "")
    if cover and not cover.startswith("/assets/scenes/"):
        return cover
    scenes = db.list_scenes(story_id)
    narrative = next((s for s in scenes if s.get("comic_url")), None)
    if narrative:
        return narrative.get("comic_url") or ""
    root = story_root(story_id)
    for scene_dir in sorted(root.glob("[0-9][0-9][0-9]")):
        panel = scene_dir / "comic" / "panel.png"
        if panel.exists():
            return url_for(int(scene_dir.name), "comic", story_id=story_id)
        bg = scene_dir / "background" / "background.png"
        if bg.exists():
            return url_for(int(scene_dir.name), "background", story_id=story_id)
    return "" if cover.startswith("/assets/scenes/") else cover


def _custom_record_to_card(record: dict) -> StoryCard:
    status = record.get("status") or "generating"
    available = status == "ready" and story_exists(record.get("id"))
    return StoryCard(
        id=record["id"],
        title=record.get("title") or "我的自定义故事",
        summary=record.get("summary") or "",
        cover_url=_custom_cover_url(record),
        scene_count=int(record.get("scene_count") or 0),
        available=available,
        status=status if status in {"ready", "generating", "failed"} else "generating",
        is_custom=True,
        error_message=record.get("error_message"),
        progress=int(record.get("progress") or 0),
        progress_label=record.get("progress_label") or "",
        public=bool(record.get("public")),
    )


def _db_row_to_card(row: dict, *, bookmarked: bool = False) -> StoryCard:
    """DB stories 行 → StoryCard，给"已收藏"和"热门"复用。"""
    status_raw = (row.get("status") or "ready").lower()
    status = status_raw if status_raw in {"ready", "generating", "failed", "locked"} else "ready"
    return StoryCard(
        id=row["id"],
        title=row.get("title") or "未命名故事",
        summary=row.get("summary") or "",
        cover_url=row.get("cover_url") or "",
        scene_count=int(row.get("scene_count") or 0),
        available=status == "ready",
        status=status,
        is_custom=not row.get("is_official"),
        error_message=row.get("error_message"),
        progress=int(row.get("progress") or 100),
        progress_label=row.get("progress_label") or "",
        public=bool(row.get("public")),
        bookmarked=bookmarked,
        owner_nickname=row.get("owner_nickname") or "",
    )


def _extract_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


def _user_from_auth(authorization: Optional[str]) -> dict | None:
    return user_by_token(_extract_token(authorization))


def _require_user(authorization: Optional[str]) -> dict:
    user = _user_from_auth(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录后再创建或管理故事。")
    return user


