"""用户自创道具 CRUD —— 需要 token 鉴权。未登录用户仍可用前端 localStorage 模式。"""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..db import (
    create_user_asset,
    delete_user_asset,
    list_user_assets,
    user_by_token,
)

router = APIRouter(prefix="/user/assets", tags=["user_assets"])


def _require_user(authorization: Optional[str]) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization.split(" ", 1)[1].strip()
    u = user_by_token(token)
    if not u:
        raise HTTPException(status_code=401, detail="登录已失效")
    return u


class UserAssetIn(BaseModel):
    id: Optional[str] = None
    name: str
    url: str
    kind: str = "object"
    origin_story_id: Optional[str] = None
    origin_scene_idx: Optional[int] = None
    created_at: Optional[int] = None


class UserAssetOut(BaseModel):
    id: str
    name: str
    url: str
    kind: str
    origin_story_id: Optional[str] = None
    origin_scene_idx: Optional[int] = None
    created_at: int


class UserAssetsResp(BaseModel):
    assets: list[UserAssetOut]


class SyncReq(BaseModel):
    assets: list[UserAssetIn]


@router.get("", response_model=UserAssetsResp)
def get_my_assets(authorization: Optional[str] = Header(default=None)) -> UserAssetsResp:
    u = _require_user(authorization)
    return UserAssetsResp(assets=[UserAssetOut(**a) for a in list_user_assets(u["id"])])


@router.post("", response_model=UserAssetOut)
def add_my_asset(payload: UserAssetIn,
                 authorization: Optional[str] = Header(default=None)) -> UserAssetOut:
    u = _require_user(authorization)
    out = create_user_asset(u["id"], payload.model_dump())
    return UserAssetOut(**out)


@router.delete("/{asset_id}")
def delete_my_asset(asset_id: str,
                    authorization: Optional[str] = Header(default=None)) -> dict:
    u = _require_user(authorization)
    ok = delete_user_asset(u["id"], asset_id)
    return {"ok": ok}


@router.post("/sync", response_model=UserAssetsResp)
def sync_my_assets(payload: SyncReq,
                   authorization: Optional[str] = Header(default=None)) -> UserAssetsResp:
    """合并本地 + 服务端资产：前端上行本地列表，服务端写入所有未存在的，然后返回合并后的全量。"""
    u = _require_user(authorization)
    existing = {a["id"] for a in list_user_assets(u["id"])}
    for a in payload.assets:
        d = a.model_dump()
        if d.get("id") and d["id"] in existing:
            continue
        create_user_asset(u["id"], d)
    return UserAssetsResp(assets=[UserAssetOut(**a) for a in list_user_assets(u["id"])])
