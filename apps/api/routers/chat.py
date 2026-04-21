from fastapi import APIRouter, HTTPException

from ..models import ChatRequest, ChatResponse
from ..services.chat_service import reply_to

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    try:
        return ChatResponse(reply=reply_to(req.scene_idx, req.user_text, req.story_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"story {req.story_id!r} not found")
