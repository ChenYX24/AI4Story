"""
公共平台 API — 阶段 2 接入账号 + 分享后会替换为真"他人分享"的数据，
当前 MVP 返回：
- stories：本机已有的所有故事（默认小红帽 + 用户做的自定义 + 未来的 v2/火焰山...）
- assets：scenes/global/{characters,objects} 里预置的资产
"""
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import SCENES_DIR
from ..scene_loader import load_story
from ..story_registry import list_custom_story_records

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


class PublicStoriesResponse(BaseModel):
    stories: list[PublicStoryCard]


class PublicAssetsResponse(BaseModel):
    assets: list[PublicAsset]


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


def _custom_to_card(rec: dict) -> PublicStoryCard:
    sid = rec.get("id", "")
    return PublicStoryCard(
        id=sid,
        title=rec.get("title") or "未命名故事",
        summary=rec.get("summary") or "",
        cover_url=rec.get("cover_url") or None,
        scene_count=int(rec.get("scene_count") or 0),
        author="社区作者",
        likes=max(12, abs(hash(sid)) % 400),
        official=False,
        category="hot",
    )


@router.get("/stories", response_model=PublicStoriesResponse)
def public_stories() -> PublicStoriesResponse:
    cards: list[PublicStoryCard] = []
    # 默认故事（官方）
    try:
        cards.append(_default_card())
    except Exception:
        pass
    # 用户自定义故事（所有人目前共享一份）— MVP 都视为"大家分享的"
    for rec in list_custom_story_records():
        try:
            cards.append(_custom_to_card(rec))
        except Exception:
            continue
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


@router.get("/assets", response_model=PublicAssetsResponse)
def public_assets() -> PublicAssetsResponse:
    return PublicAssetsResponse(assets=_iter_global_assets())
