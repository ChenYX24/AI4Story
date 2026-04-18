from fastapi import APIRouter, HTTPException

from ..config import ARK_API_KEY, DASHSCOPE_API_KEY
from ..models import InteractRequest, InteractResponse
from ..services.narrative_generator import generate_dynamic_node

router = APIRouter()


@router.post("/interact", response_model=InteractResponse)
def interact(req: InteractRequest) -> InteractResponse:
    if not req.ops:
        raise HTTPException(status_code=400, detail="至少需要一个操作")
    if not ARK_API_KEY:
        raise HTTPException(status_code=424, detail="服务器未配置 ARK_API_KEY")
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=424, detail="服务器未配置 DASHSCOPE_API_KEY（叙事生成需要）")
    try:
        payload = generate_dynamic_node(req)
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return InteractResponse(**payload)
