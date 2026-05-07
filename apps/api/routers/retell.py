"""Retell (复述) API endpoints.

POST /api/retell/start   — initialize retell session, generate hints
POST /api/retell/submit  — submit child's spoken retelling for one scene
POST /api/retell/summary — get overall retelling evaluation
"""

from fastapi import APIRouter, HTTPException

from ..models import (
    RetellStartRequest,
    RetellStartResponse,
    RetellSubmitRequest,
    RetellSubmitResponse,
    RetellSummaryRequest,
    RetellSummaryResponse,
)
from ..services.retell_service import build_summary, evaluate_submission, start_session

router = APIRouter(tags=["retell"])


@router.post("/retell/start", response_model=RetellStartResponse)
def retell_start(req: RetellStartRequest):
    try:
        return start_session(req.story_id, req.session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"story '{req.story_id}' not found")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/retell/submit", response_model=RetellSubmitResponse)
def retell_submit(req: RetellSubmitRequest):
    try:
        return evaluate_submission(req.session_id, req.scene_index, req.child_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"session '{req.session_id}' not found")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/retell/summary", response_model=RetellSummaryResponse)
def retell_summary(req: RetellSummaryRequest):
    try:
        return build_summary(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"session '{req.session_id}' not found")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
