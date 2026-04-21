from fastapi import APIRouter, HTTPException, Query

from ..scene_loader import load_story, scene_payload, story_summary_payload

router = APIRouter()


@router.get("/story")
def get_story(story_id: str | None = Query(default=None)) -> dict:
    try:
        load_story(story_id)
        return story_summary_payload(story_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"story {story_id!r} not found")


@router.get("/scene/{idx}")
def get_scene(idx: int, story_id: str | None = Query(default=None)) -> dict:
    try:
        total = len(load_story(story_id)["scenes"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"story {story_id!r} not found")
    if idx < 1 or idx > total:
        raise HTTPException(status_code=404, detail=f"scene {idx} out of range 1..{total}")
    try:
        return scene_payload(idx, story_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
