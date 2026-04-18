from fastapi import APIRouter

from ..asset_resolver import url_for
from ..models import StoriesResponse, StoryCard
from ..scene_loader import load_story

router = APIRouter()


@router.get("/stories", response_model=StoriesResponse)
def stories() -> StoriesResponse:
    story = load_story()
    scenes = story.get("scenes", [])
    first_narrative_idx = next(
        (s["scene_index"] for s in scenes if s.get("scene_type") == "叙事场景"),
        scenes[0]["scene_index"] if scenes else 1,
    )
    cover_url = url_for(first_narrative_idx, "comic")
    return StoriesResponse(
        stories=[
            StoryCard(
                id="little_red_riding_hood",
                title="小红帽",
                summary=story.get("story_summary", ""),
                cover_url=cover_url,
                scene_count=len(scenes),
                available=True,
            ),
            # placeholders for future content; available=False makes them unclickable
            StoryCard(
                id="three_little_pigs",
                title="三只小猪",
                summary="三只小猪各自盖房子，被大灰狼挑战的经典故事。",
                cover_url="",
                scene_count=0,
                available=False,
            ),
            StoryCard(
                id="snow_white",
                title="白雪公主",
                summary="公主与七个小矮人、毒苹果与真爱之吻的童话。",
                cover_url="",
                scene_count=0,
                available=False,
            ),
        ]
    )
