"""
公共平台 API — 阶段 2 接入账号 + 分享后会替换为真"他人分享"的数据，
当前 MVP 返回：
- stories：官方公开故事。用户自定义故事默认只出现在本人书架，后续通过分享码机制进入公共池。
- assets：scenes/global/{characters,objects} 里预置的资产
"""
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import SCENES_DIR
from ..scene_loader import load_story

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
    category: str = "hot"   # hot / featured / official
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
    # bundle 的封面：可以是 emoji 或 URL，前端两者兼容
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


def _default_card() -> PublicStoryCard:
    story = load_story()
    return PublicStoryCard(
        id="little_red_riding_hood",
        title="小红帽 · 森林冒险",
        summary=story.get("story_summary", ""),
        cover_url="/assets/scenes/001/comic/panel.png",
        scene_count=len(story.get("scenes", [])),
        author="漫秀官方",
        likes=512,
        official=True,
        category="official",
    )


@router.get("/stories", response_model=PublicStoriesResponse)
def public_stories() -> PublicStoriesResponse:
    cards: list[PublicStoryCard] = []
    # 默认故事（官方）
    try:
        cards.append(_default_card())
    except Exception:
        pass
    return PublicStoriesResponse(stories=cards)


def _iter_global_assets() -> list[PublicAsset]:
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
    """基于已有的全局资产自动拼几个"官方打包"。未来用户能自造 bundle 后走新表。"""
    bundles: list[PublicAssetBundle] = []
    chars = [a for a in assets if a.kind == "character"]
    objs = [a for a in assets if a.kind == "object"]

    # 小红帽人物包 — 4 位角色
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

    # 小红帽道具包 — 鲜花/篮子/床/睡帽/步枪
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

    # 未来：火焰山等其它故事的打包
    # bundles.append(PublicAssetBundle(id="bundle-huoyanshan", ...))
    return bundles


@router.get("/assets", response_model=PublicAssetsResponse)
def public_assets() -> PublicAssetsResponse:
    assets = _iter_global_assets()
    bundles = _build_official_bundles(assets)
    return PublicAssetsResponse(assets=assets, bundles=bundles)
