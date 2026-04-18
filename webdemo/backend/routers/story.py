from fastapi import APIRouter, HTTPException

from ..scene_loader import load_story, scene_payload, story_summary_payload

router = APIRouter()


@router.get("/story")
def get_story() -> dict:
    return story_summary_payload()


@router.get("/scene/{idx}")
def get_scene(idx: int) -> dict:
    total = len(load_story()["scenes"])
    if idx < 1 or idx > total:
        raise HTTPException(status_code=404, detail=f"scene {idx} out of range 1..{total}")
    try:
        return scene_payload(idx)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
