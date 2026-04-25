"""
MinIO / RustFS / S3 兼容后端。
启用：pip install minio；MINDSHOW_STORAGE=minio

env
  MINDSHOW_MINIO_BUCKET      (必)   bucket 名
  MINDSHOW_MINIO_ENDPOINT    (必)   例 110.40.183.254:9000
  MINDSHOW_MINIO_ACCESS_KEY  (必)
  MINDSHOW_MINIO_SECRET_KEY  (必)
  MINDSHOW_MINIO_SECURE      默 false；https 时设 true
  MINDSHOW_MINIO_PREFIX      默 mindshow/
  MINDSHOW_MINIO_PUBLIC_BASE 可选；若绑了 CDN / 自定义域名，URL 直接拼它
  MINDSHOW_MINIO_CREATE_BUCKET 默 true；启动时若 bucket 不存在则自动创建
"""
from __future__ import annotations

import io
import os
from typing import Optional
from urllib.parse import urlparse

from .base import StorageBackend


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class MinIOStorage(StorageBackend):
    def __init__(self) -> None:
        try:
            from minio import Minio  # type: ignore
            from minio.error import S3Error  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "MinIO 后端需要 minio，请 pip install minio；或改 env MINDSHOW_STORAGE=local"
            ) from e

        endpoint_raw = _env("MINDSHOW_MINIO_ENDPOINT", "MINDSHOW_OSS_ENDPOINT")
        if not endpoint_raw:
            raise RuntimeError("MinIO 后端需要 env MINDSHOW_MINIO_ENDPOINT")
        parsed = urlparse(endpoint_raw if "://" in endpoint_raw else f"http://{endpoint_raw}")
        self.endpoint = parsed.netloc or parsed.path
        self.secure = _as_bool(os.getenv("MINDSHOW_MINIO_SECURE"), parsed.scheme == "https")

        self.bucket = _env("MINDSHOW_MINIO_BUCKET", "MINDSHOW_OSS_BUCKET")
        if not self.bucket:
            raise RuntimeError("MinIO 后端需要 env MINDSHOW_MINIO_BUCKET")

        access_key = _env("MINDSHOW_MINIO_ACCESS_KEY", "MINDSHOW_OSS_AK_ID")
        secret_key = _env("MINDSHOW_MINIO_SECRET_KEY", "MINDSHOW_OSS_AK_SECRET")
        if not access_key or not secret_key:
            raise RuntimeError("MinIO 后端需要 env MINDSHOW_MINIO_ACCESS_KEY / MINDSHOW_MINIO_SECRET_KEY")

        self.prefix = (_env("MINDSHOW_MINIO_PREFIX", "MINDSHOW_OSS_PREFIX", default="mindshow/") or "").strip("/") + "/"
        self.public_base = _env("MINDSHOW_MINIO_PUBLIC_BASE", "MINDSHOW_OSS_PUBLIC_BASE").rstrip("/")
        self.create_bucket = _as_bool(os.getenv("MINDSHOW_MINIO_CREATE_BUCKET"), True)

        self._client = Minio(
            self.endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=self.secure,
        )
        self._s3_error = S3Error

        if self.create_bucket:
            try:
                if not self._client.bucket_exists(self.bucket):
                    self._client.make_bucket(self.bucket)
            except Exception as e:
                raise RuntimeError(f"MinIO bucket 初始化失败：{self.bucket}") from e

    def _obj(self, key: str) -> str:
        return self.prefix + self._normalize_key(key)

    def _base_url(self) -> str:
        if self.public_base:
            return self.public_base
        scheme = "https" if self.secure else "http"
        return f"{scheme}://{self.endpoint}/{self.bucket}"

    def save_bytes(self, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        kwargs = {"content_type": content_type} if content_type else {}
        self._client.put_object(
            self.bucket,
            self._obj(key),
            data=io.BytesIO(data),
            length=len(data),
            **kwargs,
        )
        return self.url_for(key)

    def read_bytes(self, key: str) -> Optional[bytes]:
        try:
            response = self._client.get_object(self.bucket, self._obj(key))
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except self._s3_error:
            return None
        except Exception:
            return None

    def exists(self, key: str) -> bool:
        try:
            self._client.stat_object(self.bucket, self._obj(key))
            return True
        except self._s3_error:
            return False
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        if not self.exists(key):
            return False
        self._client.remove_object(self.bucket, self._obj(key))
        return True

    def url_for(self, key: str) -> str:
        return f"{self._base_url()}/{self._obj(key)}"