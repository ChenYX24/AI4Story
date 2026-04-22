"""
可插拔的文件 / 图片存储后端。
运行时通过 env `MINDSHOW_STORAGE` 切换：
  - local（默认）：写本机 outputs/，URL 形如 /outputs/...（FastAPI StaticFiles 提供）
  - s3：AWS S3（需 pip install boto3）
  - oss：阿里云 OSS（需 pip install oss2）

统一接口：save_bytes(key, bytes, content_type?) -> url; read_bytes / exists / delete / url_for.
当前内部调用方：apps/api/routers/upload.py。
Seedream/TTS 等历史写盘代码将分步迁移，标记在 AGENTS.md。
"""
import os
from functools import lru_cache

from .base import StorageBackend
from .local import LocalStorage


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    kind = os.getenv("MINDSHOW_STORAGE", "local").strip().lower()
    if kind == "s3":
        from .s3 import S3Storage
        return S3Storage()
    if kind == "oss":
        from .oss import OSSStorage
        return OSSStorage()
    return LocalStorage()


__all__ = ["StorageBackend", "LocalStorage", "get_storage"]
