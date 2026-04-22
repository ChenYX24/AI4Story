"""
最小可用的 SQLite 账号库 — 零额外依赖（只用标准库 sqlite3 + hashlib + secrets）。
阶段 2 中期会迁到 SQLAlchemy + Postgres（见 ADR-002），目前只为把账户/会话/资产跑通。
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from .config import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "outputs" / "mindshow.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# 密码 salt —— 生产应该从 env 读
_SALT = os.getenv("MINDSHOW_AUTH_SALT", "mindshow-dev-salt-2026-04")


def _now() -> int:
    return int(time.time())


def _hash_password(password: str) -> str:
    return hashlib.sha256((_SALT + ":" + password).encode("utf-8")).hexdigest()


def _issue_token() -> str:
    return secrets.token_urlsafe(24)


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)  # autocommit
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
    finally:
        c.close()


def init_db() -> None:
    """建表。幂等。"""
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                nickname      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                token         TEXT,
                created_at    INTEGER NOT NULL,
                last_login_at INTEGER
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_token ON users(token)")


# ---------- 账号操作 ----------

class AuthError(Exception):
    pass


def register_user(nickname: str, password: str) -> dict:
    nickname = (nickname or "").strip()
    if not nickname:
        raise AuthError("昵称不能为空")
    if len(nickname) > 20:
        raise AuthError("昵称最多 20 个字")
    if not password or len(password) < 4:
        raise AuthError("密码至少 4 位")
    uid = "u_" + secrets.token_hex(6)
    token = _issue_token()
    with _conn() as c:
        try:
            c.execute(
                "INSERT INTO users (id, nickname, password_hash, token, created_at, last_login_at) VALUES (?,?,?,?,?,?)",
                (uid, nickname, _hash_password(password), token, _now(), _now()),
            )
        except sqlite3.IntegrityError:
            raise AuthError("这个昵称已被使用，换一个试试～")
    return {"id": uid, "nickname": nickname, "token": token}


def login_user(nickname: str, password: str) -> dict:
    nickname = (nickname or "").strip()
    with _conn() as c:
        row = c.execute(
            "SELECT id, nickname, password_hash FROM users WHERE nickname = ?", (nickname,)
        ).fetchone()
    if not row:
        raise AuthError("用户不存在")
    if row["password_hash"] != _hash_password(password):
        raise AuthError("密码错了，再试一次")
    token = _issue_token()
    with _conn() as c:
        c.execute(
            "UPDATE users SET token = ?, last_login_at = ? WHERE id = ?",
            (token, _now(), row["id"]),
        )
    return {"id": row["id"], "nickname": row["nickname"], "token": token}


def user_by_token(token: str) -> Optional[dict]:
    if not token:
        return None
    with _conn() as c:
        row = c.execute(
            "SELECT id, nickname, created_at FROM users WHERE token = ?", (token,)
        ).fetchone()
    return dict(row) if row else None


def logout_token(token: str) -> None:
    if not token:
        return
    with _conn() as c:
        c.execute("UPDATE users SET token = NULL WHERE token = ?", (token,))


# 启动时自动建表
init_db()
