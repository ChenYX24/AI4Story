"""
阿里云 OSS 后端。
启用：pip install oss2；MINDSHOW_STORAGE=oss

env
  MINDSHOW_OSS_BUCKET      (必)   bucket 名
  MINDSHOW_OSS_ENDPOINT    (必)   例 https://oss-cn-hangzhou.aliyuncs.com
  MINDSHOW_OSS_PREFIX      默 mindshow/
  MINDSHOW_OSS_PUBLIC_BASE 可选；若绑了 CDN 自定义域名（最佳实践）
  MINDSHOW_OSS_AK_ID / MINDSHOW_OSS_AK_SECRET  (必，除非用 STS)
"""
import os
from typing import Optional

from .base import StorageBackend


class OSSStorage(StorageBackend):
    def __init__(self) -> None:
        try:
            import oss2  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "OSS 后端需要 oss2，请 pip install oss2；或改 MINDSHOW_STORAGE=local"
            ) from e

        ak = os.environ["MINDSHOW_OSS_AK_ID"]
        sk = os.environ["MINDSHOW_OSS_AK_SECRET"]
        endpoint = os.environ["MINDSHOW_OSS_ENDPOINT"]
        self.bucket_name = os.environ["MINDSHOW_OSS_BUCKET"]
        self.prefix = (os.getenv("MINDSHOW_OSS_PREFIX", "mindshow/") or "").strip("/") + "/"
        self.public_base = os.getenv("MINDSHOW_OSS_PUBLIC_BASE", "").rstrip("/")

        auth = oss2.Auth(ak, sk)
        self.bucket = oss2.Bucket(auth, endpoint, self.bucket_name)
        # 从 endpoint 里解析默认 URL
        ep = endpoint.rstrip("/")
        if ep.startswith("http"):
            host = ep.split("//", 1)[1]
        else:
            host = ep
        self._default_base = f"https://{self.bucket_name}.{host}"

    def _obj(self, key: str) -> str:
        return self.prefix + self._normalize_key(key)

    def save_bytes(self, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        self.bucket.put_object(self._obj(key), data, headers=headers or None)
        return self.url_for(key)

    def read_bytes(self, key: str) -> Optional[bytes]:
        try:
            r = self.bucket.get_object(self._obj(key))
            return r.read()
        except Exception:
            return None

    def exists(self, key: str) -> bool:
        try:
            return bool(self.bucket.object_exists(self._obj(key)))
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        if not self.exists(key):
            return False
        self.bucket.delete_object(self._obj(key))
        return True

    def url_for(self, key: str) -> str:
        obj = self._obj(key)
        base = self.public_base or self._default_base
        return f"{base}/{obj}"
