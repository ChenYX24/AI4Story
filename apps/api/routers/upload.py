"""
通用图片上传 — 手绘 tab 上传 / 摄像头拍照 / 画板导出 都走这里。
接受 base64 data URL，存到 outputs/uploads/，返回可直接展示的 /outputs/... 路径。
"""
import base64
import re
import secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import OUTPUTS_ROOT

router = APIRouter(prefix="/upload", tags=["upload"])

UPLOAD_DIR = OUTPUTS_ROOT / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_DATA_URL = re.compile(r"^data:image/(png|jpe?g|webp|gif);base64,(.+)$", re.DOTALL)
_ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif"}
_MAX_BYTES = 6 * 1024 * 1024  # 6MB


class UploadImageRequest(BaseModel):
    data: str       # 可以是 data URL 或纯 base64
    ext: str | None = None  # 纯 base64 时必须
    kind: str = "misc"      # sketch / prop / avatar / cover / misc — 仅用于分组命名


class UploadImageResponse(BaseModel):
    url: str
    size: int


@router.post("/image", response_model=UploadImageResponse)
def upload_image(req: UploadImageRequest) -> UploadImageResponse:
    payload: bytes
    ext: str
    m = _DATA_URL.match(req.data.strip())
    if m:
        ext = m.group(1).lower()
        if ext == "jpeg":
            ext = "jpg"
        raw = m.group(2)
        try:
            payload = base64.b64decode(raw, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="base64 解码失败")
    else:
        # 裸 base64
        ext = (req.ext or "png").lower()
        try:
            payload = base64.b64decode(req.data, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="base64 解码失败")

    if ext not in _ALLOWED_EXT:
        raise HTTPException(status_code=415, detail=f"不支持的格式：{ext}")
    if len(payload) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="图片过大（限 6MB）")
    if len(payload) < 32:
        raise HTTPException(status_code=400, detail="图片数据为空")

    kind = re.sub(r"[^a-z0-9_-]", "", (req.kind or "misc").lower()) or "misc"
    name = f"{kind}_{secrets.token_hex(6)}.{ext}"
    out = UPLOAD_DIR / name
    out.write_bytes(payload)
    return UploadImageResponse(url=f"/outputs/uploads/{name}", size=len(payload))
