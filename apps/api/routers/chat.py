from fastapi import APIRouter, HTTPException

from ..models import ChatRequest, ChatResponse
from ..services.chat_service import ChatServiceError, reply_to

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    try:
        return ChatResponse(reply=reply_to(req.scene_idx, req.user_text, req.story_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"story {req.story_id!r} not found")
    except ChatServiceError as e:
        # 不伪造"正常"回复 —— 让前端弹 toast 让用户知道大模型暂时连不上
        raise HTTPException(status_code=502, detail=str(e))
