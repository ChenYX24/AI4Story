"""
公共平台 API。

数据源：
  - 优先 DB（stories / assets 表，is_official=1 OR public=1）
  - 文件系统回落：当 DB 里没有官方故事时（本地未跑 seed_official）从 scenes/ 读
"""
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import SCENES_DIR
from ..scene_loader import load_story
from .. import db

router = APIRouter(prefix="/public", tags=["public"])


class PublicStoryCard(BaseModel):
    id: str
    title: str
    summary: str
    cover_url: str | None = None
    scene_count: int
    author: str
    likes: int
    official: bool = False
    category: str = "hot"
    emoji_cover: str | None = None


class PublicAsset(BaseModel):
    id: str
    name: str
    kind: str      # character / object
    url: str
    svg_url: str | None = None
    category: str = "featured"


class PublicAssetBundle(BaseModel):
    id: str
    name: str
    description: str = ""
    cover_emoji: str | None = None
    cover_url: str | None = None
    kind: str      # character_pack / object_pack / mixed
    asset_ids: list[str]
    item_count: int
    official: bool = True
    likes: int = 0


class PublicStoriesResponse(BaseModel):
    stories: list[PublicStoryCard]


class PublicAssetsResponse(BaseModel):
    assets: list[PublicAsset]
    bundles: list[PublicAssetBundle] = []


def _row_to_card(row: dict) -> PublicStoryCard:
    return PublicStoryCard(
        id=row["id"],
        title=row["title"],
        summary=row.get("summary", ""),
        cover_url=row.get("cover_url"),
        scene_count=row.get("scene_count", 0),
        author="漫秀官方" if row.get("is_official") else "用户原创",
        likes=row.get("likes", 0),
        official=row.get("is_official", False),
        category="official" if row.get("is_official") else "hot",
    )


@router.get("/stories", response_model=PublicStoriesResponse)
def public_stories() -> PublicStoriesResponse:
    cards: list[PublicStoryCard] = []

    # 1) DB 里所有公开故事（官方 + 用户主动 share 的）
    rows = db.list_stories(public=True)
    for r in rows:
        cards.append(_row_to_card(r))

    # 2) 兜底：DB 里没东西时回落到文件系统的 little_red_riding_hood
    if not cards:
        try:
            story = load_story()
            cards.append(PublicStoryCard(
                id="little_red_riding_hood",
                title="小红帽 · 森林冒险",
                summary=story.get("story_summary", ""),
                cover_url="/assets/scenes/001/comic/panel.png",
                scene_count=len(story.get("scenes", [])),
                author="漫秀官方",
                likes=512,
                official=True,
                category="official",
            ))
        except Exception:
            pass
    return PublicStoriesResponse(stories=cards)


def _assets_from_db() -> list[PublicAsset]:
    rows = db.list_assets(scope="global", is_official=True)
    return [
        PublicAsset(
            id=r["id"],
            name=r["name"],
            kind=r["kind"],
            url=r["url"],
            svg_url=r.get("svg_url"),
            category="featured",
        )
        for r in rows
    ]


def _iter_global_assets_fs() -> list[PublicAsset]:
    out: list[PublicAsset] = []
    g = SCENES_DIR / "global"
    for kind_dir, kind in (("characters", "character"), ("objects", "object")):
        base: Path = g / kind_dir
        if not base.exists():
            continue
        for p in sorted(base.glob("*.png")):
            name = p.stem
            url = f"/assets/scenes/global/{kind_dir}/{p.name}"
            svg = base / f"{name}.svg"
            out.append(PublicAsset(
                id=f"{kind}-{name}",
                name=name,
                kind=kind,
                url=url,
                svg_url=f"/assets/scenes/global/{kind_dir}/{svg.name}" if svg.exists() else None,
                category="featured",
            ))
    return out


def _build_official_bundles(assets: list[PublicAsset]) -> list[PublicAssetBundle]:
    bundles: list[PublicAssetBundle] = []
    chars = [a for a in assets if a.kind == "character"]
    objs = [a for a in assets if a.kind == "object"]

    red_char_ids = [a.id for a in chars if a.name in ("小红帽", "大灰狼", "外婆", "猎人")]
    if red_char_ids:
        bundles.append(PublicAssetBundle(
            id="bundle-little-red-characters",
            name="小红帽·故事角色包",
            description="小红帽、大灰狼、外婆、猎人 四位经典角色，彩铅手绘风格。",
            cover_emoji="🧒",
            cover_url=next((a.url for a in chars if a.name == "小红帽"), None),
            kind="character_pack",
            asset_ids=red_char_ids,
            item_count=len(red_char_ids),
            official=True,
            likes=420,
        ))

    red_obj_ids = [a.id for a in objs if a.name in ("鲜花", "篮子", "床", "睡帽", "步枪")]
    if red_obj_ids:
        bundles.append(PublicAssetBundle(
            id="bundle-little-red-props",
            name="小红帽·故事道具包",
            description="鲜花、篮子、小床、睡帽、步枪——小红帽故事里全部道具。",
            cover_emoji="🧺",
            cover_url=next((a.url for a in objs if a.name == "鲜花"), None),
            kind="object_pack",
            asset_ids=red_obj_ids,
            item_count=len(red_obj_ids),
            official=True,
            likes=338,
        ))
    return bundles


@router.get("/assets", response_model=PublicAssetsResponse)
def public_assets() -> PublicAssetsResponse:
    assets = _assets_from_db()
    if not assets:
        assets = _iter_global_assets_fs()
    bundles = _build_official_bundles(assets)
    return PublicAssetsResponse(assets=assets, bundles=bundles)
