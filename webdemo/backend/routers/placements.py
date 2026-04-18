from fastapi import APIRouter, HTTPException

from ..models import PlacementRequest, PlacementResponse
from ..scene_loader import load_story
from ..services.placement_service import get_placements

router = APIRouter()


@router.post("/placements", response_model=PlacementResponse)
def placements(req: PlacementRequest) -> PlacementResponse:
    total = len(load_story()["scenes"])
    if req.scene_idx < 1 or req.scene_idx > total:
        raise HTTPException(status_code=404, detail=f"scene {req.scene_idx} out of range")
    try:
        items = get_placements(req.scene_idx)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return PlacementResponse(placements=items)
