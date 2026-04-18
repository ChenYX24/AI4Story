from fastapi import APIRouter, HTTPException

from ..config import ARK_API_KEY, DASHSCOPE_API_KEY
from ..models import (
    BatchCreatePropsRequest,
    BatchCreatePropsResponse,
    CreatePropRequest,
    CreatePropResponse,
    SmartCreatePropsRequest,
    SmartCreatePropsResponse,
)
from ..services.prop_generator import (
    create_custom_prop,
    create_custom_props_batch,
    smart_create_props,
)

router = APIRouter()


@router.post("/create_prop", response_model=CreatePropResponse)
def create_prop(req: CreatePropRequest) -> CreatePropResponse:
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="物品名不能为空")
    if not ARK_API_KEY:
        raise HTTPException(status_code=424, detail="服务器未配置 ARK_API_KEY")
    try:
        url, _ = create_custom_prop(req.session_id, req.name.strip(), req.description)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return CreatePropResponse(name=req.name.strip(), url=url)


@router.post("/create_props_batch", response_model=BatchCreatePropsResponse)
def create_props_batch(req: BatchCreatePropsRequest) -> BatchCreatePropsResponse:
    if not req.items:
        raise HTTPException(status_code=400, detail="请先填入至少 1 个物品")
    if len(req.items) > 9:
        raise HTTPException(status_code=400, detail="一次最多生成 9 个")
    if not ARK_API_KEY:
        raise HTTPException(status_code=424, detail="服务器未配置 ARK_API_KEY")
    try:
        results = create_custom_props_batch(
            req.session_id,
            [{"name": it.name, "description": it.description} for it in req.items],
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return BatchCreatePropsResponse(
        props=[CreatePropResponse(name=r["name"], url=r["url"]) for r in results]
    )


@router.post("/create_props_smart", response_model=SmartCreatePropsResponse)
def create_props_smart(req: SmartCreatePropsRequest) -> SmartCreatePropsResponse:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="请先说明要创造什么")
    if not ARK_API_KEY:
        raise HTTPException(status_code=424, detail="服务器未配置 ARK_API_KEY")
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=424, detail="服务器未配置 DASHSCOPE_API_KEY（解析需要）")
    try:
        parsed, results = smart_create_props(
            session_id=req.session_id,
            scene_idx=req.scene_idx,
            text=req.text,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return SmartCreatePropsResponse(
        parsed=parsed,
        props=[CreatePropResponse(name=r["name"], url=r["url"]) for r in results],
    )
