"""资产打包 + 分享码 —— D4/D5。
创建 pack 需要登录（记录 owner）；import 只要有码即可，任何用户（包括游客）都能拉取内容。"""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..db import (
    create_asset_pack,
    get_asset_pack,
    list_public_packs,
    user_assets_by_ids,
    user_by_token,
)

router = APIRouter(prefix="/packs", tags=["asset_packs"])


def _current_user(authorization: Optional[str]) -> Optional[dict]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    return user_by_token(token)


class PackCreateReq(BaseModel):
    name: str
    description: Optional[str] = ""
    asset_ids: list[str]
    public: bool = False


class AssetItem(BaseModel):
    id: str
    name: str
    url: str
    kind: str
    origin_story_id: Optional[str] = None
    origin_scene_idx: Optional[int] = None
    created_at: Optional[int] = None


class PackOut(BaseModel):
    code: str
    name: str
    description: str
    public: bool
    asset_ids: list[str]
    assets: list[AssetItem] = []
    created_at: int
    owner_user_id: Optional[str] = None


@router.post("", response_model=PackOut)
def create_pack(payload: PackCreateReq,
                authorization: Optional[str] = Header(default=None)) -> PackOut:
    if not payload.asset_ids:
        raise HTTPException(status_code=400, detail="至少选一件资产")
    u = _current_user(authorization)
    owner = u["id"] if u else None
    r = create_asset_pack(owner, payload.name or "我分享的道具包",
                          payload.description or "", payload.asset_ids, payload.public)
    assets_map = user_assets_by_ids(payload.asset_ids)
    return PackOut(
        code=r["code"],
        name=r["name"], description=r["description"], public=r["public"],
        asset_ids=r["asset_ids"],
        assets=[AssetItem(**assets_map[aid]) for aid in r["asset_ids"] if aid in assets_map],
        created_at=r["created_at"], owner_user_id=owner,
    )


@router.get("/{code}", response_model=PackOut)
def get_pack(code: str) -> PackOut:
    r = get_asset_pack(code)
    if not r:
        raise HTTPException(status_code=404, detail=f"分享码 {code} 不存在")
    assets_map = user_assets_by_ids(r["asset_ids"])
    return PackOut(
        code=r["code"], name=r["name"], description=r["description"],
        public=r["public"], asset_ids=r["asset_ids"],
        assets=[AssetItem(**assets_map[aid]) for aid in r["asset_ids"] if aid in assets_map],
        created_at=r["created_at"], owner_user_id=r["owner_user_id"],
    )


class PublicPacksResp(BaseModel):
    packs: list[PackOut]


@router.get("/", response_model=PublicPacksResp)
def list_packs() -> PublicPacksResp:
    raw = list_public_packs(50)
    all_ids: list[str] = []
    for p in raw:
        all_ids.extend(p["asset_ids"])
    assets_map = user_assets_by_ids(all_ids)
    packs = [
        PackOut(
            code=p["code"], name=p["name"], description=p["description"],
            public=True, asset_ids=p["asset_ids"],
            assets=[AssetItem(**assets_map[aid]) for aid in p["asset_ids"] if aid in assets_map],
            created_at=p["created_at"], owner_user_id=p["owner_user_id"],
        )
        for p in raw
    ]
    return PublicPacksResp(packs=packs)
