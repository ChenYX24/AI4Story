from fastapi import APIRouter, HTTPException, Query

from ..models import ChatRequest, ChatResponse, ChatSuggestionsResponse
from ..services.chat_service import ChatServiceError, reply_to
from ..services.suggestion_service import get_scene_questions

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    try:
        return ChatResponse(reply=reply_to(req.scene_idx, req.user_text, req.story_id, req.session_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"story {req.story_id!r} not found")
    except ChatServiceError as e:
        # 不伪造"正常"回复 —— 让前端弹 toast 让用户知道大模型暂时连不上
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/chat/suggestions", response_model=ChatSuggestionsResponse)
def chat_suggestions(
    scene_idx: int = Query(..., ge=1),
    story_id: str | None = Query(default=None),
) -> ChatSuggestionsResponse:
    try:
        return ChatSuggestionsResponse(questions=get_scene_questions(scene_idx, story_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"story {story_id!r} not found")
