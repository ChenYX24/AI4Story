from typing import Literal

from pydantic import BaseModel, Field


class Transform(BaseModel):
    name: str
    kind: Literal["character", "object"]
    x: float = Field(ge=-0.1, le=1.1)
    y: float = Field(ge=-0.1, le=1.1)
    scale: float = Field(default=1.0, ge=0.2, le=4.0)
    rotation: float = Field(default=0.0, ge=-360.0, le=360.0)
    custom_url: str | None = None


class CustomProp(BaseModel):
    name: str
    url: str


class Operation(BaseModel):
    subject: str | None = None
    subject_kind: Literal["character", "object"] | None = None
    target: str | None = None
    target_kind: Literal["character", "object"] | None = None
    action: str


class InteractRequest(BaseModel):
    story_id: str | None = None
    session_id: str
    scene_idx: int
    placements: list[Transform] = Field(default_factory=list)
    ops: list[Operation]
    custom_props: list[CustomProp] = Field(default_factory=list)


class DialogueLine(BaseModel):
    speaker: str
    content: str
    tone: str = ""


class StoryboardLine(BaseModel):
    speaker: str
    text: str
    kind: Literal["narration", "dialogue"]
    tone: str = ""


class InteractResponse(BaseModel):
    node_id: str
    type: Literal["narrative"] = "narrative"
    summary: str
    narration: str
    dialogue: list[DialogueLine]
    storyboard: list[StoryboardLine]
    comic_url: str
    thumbnail_url: str


class PlacementRequest(BaseModel):
    story_id: str | None = None
    scene_idx: int


class PlacementItem(BaseModel):
    name: str
    kind: Literal["character", "object"]
    x: float
    y: float
    scale: float = 1.0
    rotation: float = 0.0


class PlacementResponse(BaseModel):
    placements: list[PlacementItem]


class CreatePropRequest(BaseModel):
    session_id: str
    scene_idx: int
    name: str
    description: str | None = None
    # 可选：来自用户上传 / 画板 / 摄像头的参考图 URL（相对 /outputs/... 或绝对 http）。
    # 提供时，AI 生成的 prompt 会带上"用户参考图"的提示。
    reference_image_url: str | None = None
    # True = 直接以 reference_image_url 作为道具图（不调 AI，跳过 Seedream），适合画板/手绘原样保留
    skip_ai: bool = False


class CreatePropResponse(BaseModel):
    name: str
    url: str
    reference_image_url: str | None = None


class TTSItem(BaseModel):
    text: str
    voice: str | None = None
    tone: str | None = None
    speaker: str | None = None


class TTSBatchRequest(BaseModel):
    items: list[TTSItem]


class TTSBatchResponseItem(BaseModel):
    index: int
    audio_b64: str
    format: str


class TTSBatchResponse(BaseModel):
    items: list[TTSBatchResponseItem]


class BatchPropItem(BaseModel):
    name: str
    description: str | None = None


class BatchCreatePropsRequest(BaseModel):
    session_id: str
    scene_idx: int
    items: list[BatchPropItem]


class BatchCreatePropsResponse(BaseModel):
    props: list[CreatePropResponse]


class SmartCreatePropsRequest(BaseModel):
    session_id: str
    scene_idx: int
    text: str


class SmartCreatePropsResponse(BaseModel):
    parsed: list[str]     # the names as understood by Qwen
    props: list[CreatePropResponse]


class ChatRequest(BaseModel):
    story_id: str | None = None
    session_id: str
    scene_idx: int
    user_text: str


class ChatResponse(BaseModel):
    reply: str


class StoryCard(BaseModel):
    id: str
    title: str
    summary: str
    cover_url: str
    scene_count: int
    available: bool = True
    status: Literal["ready", "generating", "locked", "failed"] = "ready"
    is_custom: bool = False
    error_message: str | None = None
    progress: int = 0
    progress_label: str = ""


class StoriesResponse(BaseModel):
    stories: list[StoryCard]


class CustomStoryCreateRequest(BaseModel):
    text: str
    title: str = ""


class ReportInteraction(BaseModel):
    scene_idx: int
    interaction_goal: str = ""
    ops: list[Operation] = Field(default_factory=list)
    custom_props: list[CustomProp] = Field(default_factory=list)
    dynamic_summary: str = ""
    comic_url: str | None = None


class ReportRequest(BaseModel):
    session_id: str
    story_id: str
    interactions: list[ReportInteraction] = Field(default_factory=list)


class ReportResponse(BaseModel):
    share: dict                   # {summary, honor_title, achievements:[{icon,text}]}
    kid_section: dict             # {title, your_story, original_story, differences:[...], questions:[...]}
    parent_section: dict          # {title, traits:[...], weaknesses:[...], observations:[...], suggestions:[...], metrics:[{name,value,description}]}
