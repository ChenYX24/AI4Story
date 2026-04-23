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
        # 用户自创道具（互动页 AI / 上传 / 画板，登录后同步服务端）
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_assets (
                id            TEXT PRIMARY KEY,
                user_id       TEXT NOT NULL,
                name          TEXT NOT NULL,
                url           TEXT NOT NULL,
                kind          TEXT NOT NULL,
                origin_story_id   TEXT,
                origin_scene_idx  INTEGER,
                created_at    INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_assets_user ON user_assets(user_id)")
        # 分享码：把一个或多个 user_assets 打包，生成短码供他人导入
        c.execute("""
            CREATE TABLE IF NOT EXISTS asset_packs (
                code          TEXT PRIMARY KEY,
                owner_user_id TEXT,
                name          TEXT NOT NULL,
                description   TEXT,
                asset_ids     TEXT NOT NULL,
                public        INTEGER NOT NULL DEFAULT 0,
                created_at    INTEGER NOT NULL,
                FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_asset_packs_public ON asset_packs(public)")


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


# ---------- 用户自创道具 (user_assets) ----------

def list_user_assets(user_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, name, url, kind, origin_story_id, origin_scene_idx, created_at "
            "FROM user_assets WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def create_user_asset(user_id: str, a: dict) -> dict:
    aid = a.get("id") or ("ua_" + secrets.token_hex(6))
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO user_assets "
            "(id, user_id, name, url, kind, origin_story_id, origin_scene_idx, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                aid, user_id,
                a["name"], a["url"], a.get("kind", "object"),
                a.get("origin_story_id"), a.get("origin_scene_idx"),
                int(a.get("created_at") or _now() * 1000),
            ),
        )
    return {
        "id": aid, "name": a["name"], "url": a["url"], "kind": a.get("kind", "object"),
        "origin_story_id": a.get("origin_story_id"),
        "origin_scene_idx": a.get("origin_scene_idx"),
        "created_at": int(a.get("created_at") or _now() * 1000),
    }


def delete_user_asset(user_id: str, asset_id: str) -> bool:
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM user_assets WHERE user_id = ? AND id = ?",
            (user_id, asset_id),
        )
        return cur.rowcount > 0


def user_assets_by_ids(ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    placeholders = ",".join(["?"] * len(ids))
    with _conn() as c:
        rows = c.execute(
            f"SELECT id, name, url, kind, origin_story_id, origin_scene_idx, created_at "
            f"FROM user_assets WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
    return {r["id"]: dict(r) for r in rows}


# ---------- 分享码 (asset_packs) ----------

import json as _json


def _gen_share_code() -> str:
    # 6 位大写字母+数字；简单避免易混字（0/O/1/I）
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


def create_asset_pack(owner_user_id: Optional[str], name: str, description: str,
                     asset_ids: list[str], public: bool = False) -> dict:
    # 生成不冲突的 6 位码
    for _ in range(10):
        code = _gen_share_code()
        with _conn() as c:
            existing = c.execute("SELECT 1 FROM asset_packs WHERE code = ?", (code,)).fetchone()
            if existing:
                continue
            c.execute(
                "INSERT INTO asset_packs (code, owner_user_id, name, description, asset_ids, public, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (code, owner_user_id, name, description or "",
                 _json.dumps(asset_ids, ensure_ascii=False), 1 if public else 0, _now()),
            )
            return {
                "code": code, "name": name, "description": description or "",
                "asset_ids": list(asset_ids), "public": bool(public), "created_at": _now(),
            }
    raise RuntimeError("无法生成唯一分享码，请稍后重试")


def get_asset_pack(code: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT code, owner_user_id, name, description, asset_ids, public, created_at "
            "FROM asset_packs WHERE code = ?",
            (code.upper(),),
        ).fetchone()
    if not row:
        return None
    return {
        "code": row["code"], "owner_user_id": row["owner_user_id"],
        "name": row["name"], "description": row["description"],
        "asset_ids": _json.loads(row["asset_ids"] or "[]"),
        "public": bool(row["public"]),
        "created_at": row["created_at"],
    }


def list_public_packs(limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT code, owner_user_id, name, description, asset_ids, public, created_at "
            "FROM asset_packs WHERE public = 1 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for row in rows:
        out.append({
            "code": row["code"], "owner_user_id": row["owner_user_id"],
            "name": row["name"], "description": row["description"],
            "asset_ids": _json.loads(row["asset_ids"] or "[]"),
            "public": True, "created_at": row["created_at"],
        })
    return out


# 启动时自动建表
init_db()
