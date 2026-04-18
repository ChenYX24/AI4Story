from fastapi import APIRouter

from ..models import ChatRequest, ChatResponse
from ..services.chat_service import reply_to

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    return ChatResponse(reply=reply_to(req.scene_idx, req.user_text))
