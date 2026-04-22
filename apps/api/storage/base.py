from abc import ABC, abstractmethod
from typing import Optional


class StorageBackend(ABC):
    """
    存储后端抽象。所有后端用同一个 "key" 做标识 —— 以 `/` 分段的相对路径，
    例如 `uploads/prop_ab12cd.png`、`webdemo/s_xxx/frame_03.png`。

    key 约定：
      - 不要以 `/` 开头
      - 不要含 `..`
      - 仅允许 [A-Za-z0-9 中英混合 - _ . /]
    """

    @abstractmethod
    def save_bytes(
        self,
        key: str,
        data: bytes,
        content_type: Optional[str] = None,
    ) -> str:
        """保存字节，返回可供浏览器直接访问的 URL（相对或绝对）。"""

    @abstractmethod
    def read_bytes(self, key: str) -> Optional[bytes]:
        """读出字节，不存在返回 None。"""

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除；成功 True，不存在 False。"""

    @abstractmethod
    def url_for(self, key: str) -> str:
        """根据已知 key 返回访问 URL（不检查是否存在）。"""

    # 工具：子类可复用
    @staticmethod
    def _normalize_key(key: str) -> str:
        k = (key or "").lstrip("/")
        if ".." in k.split("/"):
            raise ValueError(f"invalid key: {key!r}")
        return k
