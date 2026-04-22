from pathlib import Path
from typing import Optional

from ..config import OUTPUTS_ROOT
from .base import StorageBackend


class LocalStorage(StorageBackend):
    """
    本机磁盘存储。写到 OUTPUTS_ROOT/<key>，URL 为 /outputs/<key>
    （main.py 挂载了 /outputs -> StaticFiles(OUTPUTS_ROOT)）。
    """

    def __init__(self, root: Optional[Path] = None):
        self.root = (root or OUTPUTS_ROOT).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, key: str) -> Path:
        k = self._normalize_key(key)
        p = (self.root / k).resolve()
        # 防越狱：拒绝跳出 root
        if not str(p).startswith(str(self.root)):
            raise ValueError(f"key escapes root: {key!r}")
        return p

    def save_bytes(self, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        _ = content_type  # local 不依赖 MIME
        p = self._p(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return self.url_for(key)

    def read_bytes(self, key: str) -> Optional[bytes]:
        p = self._p(key)
        return p.read_bytes() if p.is_file() else None

    def exists(self, key: str) -> bool:
        return self._p(key).is_file()

    def delete(self, key: str) -> bool:
        p = self._p(key)
        if p.is_file():
            p.unlink()
            return True
        return False

    def url_for(self, key: str) -> str:
        return f"/outputs/{self._normalize_key(key)}"
