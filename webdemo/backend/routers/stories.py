from fastapi import APIRouter, HTTPException

from ..asset_resolver import url_for
from ..models import CustomStoryCreateRequest, StoriesResponse, StoryCard
from ..scene_loader import load_story
from ..services.custom_story_service import submit_custom_story
from ..story_registry import delete_custom_story_record, list_custom_story_records, story_exists, update_custom_story_record

router = APIRouter()


@router.get("/stories", response_model=StoriesResponse)
def stories() -> StoriesResponse:
    custom_cards = _build_custom_story_cards()
    if custom_cards:
        return StoriesResponse(stories=custom_cards)
    default_story = load_story()
    return StoriesResponse(stories=[_build_default_story_card(default_story)])


@router.post("/stories/custom", response_model=StoryCard)
def create_custom_story(req: CustomStoryCreateRequest) -> StoryCard:
    try:
        record = submit_custom_story(req.text, title=req.title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=424, detail=str(exc))
    return _custom_record_to_card(record)


@router.delete("/stories/custom/{story_id}", status_code=204)
def delete_custom_story(story_id: str) -> None:
    if not delete_custom_story_record(story_id):
        raise HTTPException(status_code=404, detail="故事不存在。")


@router.patch("/stories/custom/{story_id}", response_model=StoryCard)
def patch_custom_story(story_id: str, body: dict) -> StoryCard:
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空。")
    record = update_custom_story_record(story_id, title=title)
    return _custom_record_to_card(record)


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


def _build_custom_story_cards() -> list[StoryCard]:
    return [_custom_record_to_card(record) for record in list_custom_story_records()]


def _custom_record_to_card(record: dict) -> StoryCard:
    status = record.get("status") or "generating"
    available = status == "ready" and story_exists(record.get("id"))
    return StoryCard(
        id=record["id"],
        title=record.get("title") or "我的自定义故事",
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


