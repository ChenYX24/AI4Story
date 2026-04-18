from fastapi import APIRouter, HTTPException

from ..asset_resolver import url_for
from ..models import CustomStoryCreateRequest, StoriesResponse, StoryCard
from ..scene_loader import load_story
from ..services.custom_story_service import submit_custom_story
from ..story_registry import delete_custom_story_record, list_custom_story_records, story_exists

router = APIRouter()


@router.get("/stories", response_model=StoriesResponse)
def stories() -> StoriesResponse:
    default_story = load_story()
    cards = [_build_default_story_card(default_story)]
    cards.extend(_build_custom_story_cards())
    cards.extend(_build_placeholder_cards())
    return StoriesResponse(stories=cards)


@router.post("/stories/custom", response_model=StoryCard)
def create_custom_story(req: CustomStoryCreateRequest) -> StoryCard:
    try:
        record = submit_custom_story(req.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=424, detail=str(exc))
    return _custom_record_to_card(record)


@router.delete("/stories/custom/{story_id}", status_code=204)
def delete_custom_story(story_id: str) -> None:
    if not delete_custom_story_record(story_id):
        raise HTTPException(status_code=404, detail="故事不存在。")


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


def _build_placeholder_cards() -> list[StoryCard]:
    return [
        StoryCard(
            id="three_little_pigs",
            title="三只小猪",
            summary="三只小猪各自盖房子，被大灰狼挑战的经典故事。",
            cover_url="",
            scene_count=0,
            available=False,
            status="locked",
        ),
        StoryCard(
            id="snow_white",
            title="白雪公主",
            summary="公主与七个小矮人、毒苹果与真爱之吻的童话故事。",
            cover_url="",
            scene_count=0,
            available=False,
            status="locked",
        ),
    ]



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
    )


def _build_placeholder_cards() -> list[StoryCard]:
    return [
        StoryCard(
            id="three_little_pigs",
            title="三只小猪",
            summary="三只小猪各自盖房子，被大灰狼挑战的经典故事。",
            cover_url="",
            scene_count=0,
            available=False,
            status="locked",
        ),
        StoryCard(
            id="snow_white",
            title="白雪公主",
            summary="公主与七个小矮人、毒苹果与真爱之吻的童话故事。",
            cover_url="",
            scene_count=0,
            available=False,
            status="locked",
        ),
    ]
