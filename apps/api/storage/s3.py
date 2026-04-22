"""
AWS S3 / S3 兼容（MinIO / R2 / DO Spaces）后端。
启用：pip install boto3；MINDSHOW_STORAGE=s3

env
  MINDSHOW_S3_BUCKET      (必)    桶名
  MINDSHOW_S3_REGION      默 us-east-1
  MINDSHOW_S3_ENDPOINT    可选；S3 兼容服务（如 https://<account>.r2.cloudflarestorage.com）
  MINDSHOW_S3_PREFIX      默 mindshow/   对象 key 前缀
  MINDSHOW_S3_PUBLIC_BASE 可选；若配了 CDN/自定义域名，URL 直接拼它；否则用虚拟 host 风格
  MINDSHOW_S3_ACL         默 public-read；私桶可设 private（需改签名 URL 流程）
  AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN — 走 boto3 默认 credential chain
"""
import os
from typing import Optional

from .base import StorageBackend


class S3Storage(StorageBackend):
    def __init__(self) -> None:
        try:
            import boto3  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "S3 后端需要 boto3，请 pip install boto3；"
                "或改 env MINDSHOW_STORAGE=local"
            ) from e

        self.bucket = os.environ["MINDSHOW_S3_BUCKET"]
        self.region = os.getenv("MINDSHOW_S3_REGION", "us-east-1")
        self.prefix = (os.getenv("MINDSHOW_S3_PREFIX", "mindshow/") or "").strip("/") + "/"
        self.public_base = os.getenv("MINDSHOW_S3_PUBLIC_BASE", "").rstrip("/")
        self.acl = os.getenv("MINDSHOW_S3_ACL", "public-read")
        endpoint = os.getenv("MINDSHOW_S3_ENDPOINT") or None

        session = boto3.session.Session(region_name=self.region)
        self.s3 = session.client("s3", endpoint_url=endpoint)

    # 把外部 key 映射成带 prefix 的对象 key
    def _obj(self, key: str) -> str:
        return self.prefix + self._normalize_key(key)

    def save_bytes(self, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        kwargs = {"Bucket": self.bucket, "Key": self._obj(key), "Body": data, "ACL": self.acl}
        if content_type:
            kwargs["ContentType"] = content_type
        self.s3.put_object(**kwargs)
        return self.url_for(key)

    def read_bytes(self, key: str) -> Optional[bytes]:
        try:
            r = self.s3.get_object(Bucket=self.bucket, Key=self._obj(key))
            return r["Body"].read()
        except self.s3.exceptions.NoSuchKey:  # type: ignore[attr-defined]
            return None
        except Exception:
            # e.g. 403 / transient — treat as not found for simplicity
            return None

    def exists(self, key: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket, Key=self._obj(key))
            return True
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        if not self.exists(key):
            return False
        self.s3.delete_object(Bucket=self.bucket, Key=self._obj(key))
        return True

    def url_for(self, key: str) -> str:
        obj = self._obj(key)
        if self.public_base:
            return f"{self.public_base}/{obj}"
        # 虚拟 host 风格（需桶名合规）
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{obj}"
