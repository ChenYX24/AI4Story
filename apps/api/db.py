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
        # 游玩会话（混合存储：前端 localStorage 缓存 + 后端持久化）
        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id            TEXT PRIMARY KEY,
                user_id       TEXT NOT NULL,
                story_id      TEXT NOT NULL,
                play_state    TEXT NOT NULL DEFAULT '{}',
                status        TEXT NOT NULL DEFAULT 'playing',
                created_at    INTEGER NOT NULL,
                updated_at    INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_story ON sessions(user_id, story_id)")
        # 统一内容表：官方 / 用户原创故事都进这张表，is_official + owner_user_id 字段区分。
        c.execute("""
            CREATE TABLE IF NOT EXISTS stories (
                id              TEXT PRIMARY KEY,
                title           TEXT NOT NULL,
                summary         TEXT NOT NULL DEFAULT '',
                cover_url       TEXT,
                scene_count     INTEGER NOT NULL DEFAULT 0,
                status          TEXT NOT NULL DEFAULT 'ready',
                error_message   TEXT,
                progress        INTEGER NOT NULL DEFAULT 100,
                progress_label  TEXT,
                is_official     INTEGER NOT NULL DEFAULT 0,
                public          INTEGER NOT NULL DEFAULT 0,
                owner_user_id   TEXT,
                raw_meta        TEXT NOT NULL DEFAULT '{}',
                likes           INTEGER NOT NULL DEFAULT 0,
                input_text      TEXT NOT NULL DEFAULT '',
                created_at      INTEGER NOT NULL,
                updated_at      INTEGER NOT NULL,
                FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_stories_owner ON stories(owner_user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_stories_official_public ON stories(is_official, public)")
        # 每个故事的场景 — comic_url / background_url 直接保存 OSS URL，避免运行时拼路径。
        c.execute("""
            CREATE TABLE IF NOT EXISTS scenes (
                id                TEXT PRIMARY KEY,
                story_id          TEXT NOT NULL,
                scene_index       INTEGER NOT NULL,
                scene_type        TEXT NOT NULL,
                title             TEXT NOT NULL DEFAULT '',
                narration         TEXT NOT NULL DEFAULT '',
                interaction_goal  TEXT,
                initial_frame     TEXT,
                event_outcome     TEXT,
                comic_url         TEXT,
                background_url    TEXT,
                raw_json          TEXT NOT NULL DEFAULT '{}',
                created_at        INTEGER NOT NULL,
                UNIQUE(story_id, scene_index),
                FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_scenes_story ON scenes(story_id)")
        # 统一资产表 — 官方角色/道具、scene-local、用户创作 全在这里，is_official + scope + owner_user_id 区分。
        c.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                id                TEXT PRIMARY KEY,
                name              TEXT NOT NULL,
                kind              TEXT NOT NULL,
                url               TEXT NOT NULL,
                svg_url           TEXT,
                description       TEXT NOT NULL DEFAULT '',
                scope             TEXT NOT NULL,
                story_id          TEXT,
                scene_index       INTEGER,
                is_official       INTEGER NOT NULL DEFAULT 0,
                public            INTEGER NOT NULL DEFAULT 0,
                owner_user_id     TEXT,
                origin_story_id   TEXT,
                origin_scene_idx  INTEGER,
                created_at        INTEGER NOT NULL,
                FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_assets_owner ON assets(owner_user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_assets_scope_story ON assets(scope, story_id, scene_index)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_assets_official ON assets(is_official, scope)")


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
        existing = c.execute("SELECT user_id FROM user_assets WHERE id = ?", (aid,)).fetchone()
        if existing and existing["user_id"] != user_id:
            aid = "ua_" + secrets.token_hex(6)
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


def list_user_packs(user_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT code, owner_user_id, name, description, asset_ids, public, created_at "
            "FROM asset_packs WHERE owner_user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [{
        "code": r["code"], "owner_user_id": r["owner_user_id"],
        "name": r["name"], "description": r["description"],
        "asset_ids": _json.loads(r["asset_ids"] or "[]"),
        "public": bool(r["public"]), "created_at": r["created_at"],
    } for r in rows]


def update_asset_pack(code: str, owner_user_id: str, *,
                      name: Optional[str] = None, description: Optional[str] = None,
                      asset_ids: Optional[list[str]] = None, public: Optional[bool] = None) -> bool:
    pack = get_asset_pack(code)
    if not pack or pack.get("owner_user_id") != owner_user_id:
        return False
    sets, vals = [], []
    if name is not None:
        sets.append("name = ?"); vals.append(name)
    if description is not None:
        sets.append("description = ?"); vals.append(description)
    if asset_ids is not None:
        sets.append("asset_ids = ?"); vals.append(_json.dumps(asset_ids, ensure_ascii=False))
    if public is not None:
        sets.append("public = ?"); vals.append(1 if public else 0)
    if not sets:
        return True
    vals.append(code)
    with _conn() as c:
        c.execute(f"UPDATE asset_packs SET {', '.join(sets)} WHERE code = ?", vals)
    return True


def delete_asset_pack(code: str, owner_user_id: str) -> bool:
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM asset_packs WHERE code = ? AND owner_user_id = ?",
            (code, owner_user_id),
        )
        return cur.rowcount > 0


# ---------- 游玩会话 (sessions) ----------

def create_session(user_id: str, story_id: str, play_state: str) -> dict:
    sid = "sess_" + secrets.token_hex(8)
    now = _now()
    with _conn() as c:
        c.execute(
            "INSERT INTO sessions (id, user_id, story_id, play_state, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (sid, user_id, story_id, play_state, "playing", now, now),
        )
    return {"id": sid, "user_id": user_id, "story_id": story_id,
            "play_state": _json.loads(play_state), "status": "playing",
            "created_at": now, "updated_at": now}


def update_session(session_id: str, user_id: str, play_state: str,
                   status: Optional[str] = None) -> bool:
    sets = ["play_state = ?", "updated_at = ?"]
    vals: list = [play_state, _now()]
    if status:
        sets.append("status = ?"); vals.append(status)
    vals += [session_id, user_id]
    with _conn() as c:
        cur = c.execute(
            f"UPDATE sessions SET {', '.join(sets)} WHERE id = ? AND user_id = ?", vals,
        )
        return cur.rowcount > 0


def get_sessions_for_story(user_id: str, story_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, user_id, story_id, play_state, status, created_at, updated_at "
            "FROM sessions WHERE user_id = ? AND story_id = ? ORDER BY updated_at DESC",
            (user_id, story_id),
        ).fetchall()
    return [{
        "id": r["id"], "user_id": r["user_id"], "story_id": r["story_id"],
        "play_state": _json.loads(r["play_state"] or "{}"),
        "status": r["status"], "created_at": r["created_at"], "updated_at": r["updated_at"],
    } for r in rows]


def delete_session(session_id: str, user_id: str) -> bool:
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        return cur.rowcount > 0


# ---------- 统一内容表：stories / scenes / assets ----------

def upsert_story(s: dict) -> dict:
    """官方/用户故事统一入口。要求字段：id, title。其余给默认值。"""
    sid = s["id"]
    now = _now()
    raw_meta = s.get("raw_meta")
    if isinstance(raw_meta, dict):
        raw_meta = _json.dumps(raw_meta, ensure_ascii=False)
    with _conn() as c:
        c.execute(
            """
            INSERT INTO stories
                (id, title, summary, cover_url, scene_count, status, error_message,
                 progress, progress_label, is_official, public, owner_user_id, raw_meta,
                 likes, input_text, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                summary = excluded.summary,
                cover_url = excluded.cover_url,
                scene_count = excluded.scene_count,
                status = excluded.status,
                error_message = excluded.error_message,
                progress = excluded.progress,
                progress_label = excluded.progress_label,
                is_official = excluded.is_official,
                public = excluded.public,
                owner_user_id = excluded.owner_user_id,
                raw_meta = excluded.raw_meta,
                likes = excluded.likes,
                input_text = excluded.input_text,
                updated_at = excluded.updated_at
            """,
            (
                sid,
                s.get("title", ""),
                s.get("summary", ""),
                s.get("cover_url"),
                int(s.get("scene_count", 0) or 0),
                s.get("status", "ready"),
                s.get("error_message"),
                int(s.get("progress", 100) or 0),
                s.get("progress_label"),
                1 if s.get("is_official") else 0,
                1 if s.get("public") else 0,
                s.get("owner_user_id"),
                raw_meta or "{}",
                int(s.get("likes", 0) or 0),
                s.get("input_text", ""),
                int(s.get("created_at") or now),
                now,
            ),
        )
    return get_story(sid) or {}


def get_story(story_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
    if not row:
        return None
    return _row_to_story(row)


def list_stories(*, owner_user_id: Optional[str] = None, public: Optional[bool] = None,
                 is_official: Optional[bool] = None) -> list[dict]:
    sql = "SELECT * FROM stories WHERE 1=1"
    args: list = []
    if owner_user_id is not None:
        sql += " AND owner_user_id = ?"; args.append(owner_user_id)
    if public is not None:
        sql += " AND public = ?"; args.append(1 if public else 0)
    if is_official is not None:
        sql += " AND is_official = ?"; args.append(1 if is_official else 0)
    sql += " ORDER BY is_official DESC, updated_at DESC"
    with _conn() as c:
        rows = c.execute(sql, args).fetchall()
    return [_row_to_story(r) for r in rows]


def delete_story(story_id: str) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM stories WHERE id = ?", (story_id,))
        return cur.rowcount > 0


def _row_to_story(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "summary": row["summary"],
        "cover_url": row["cover_url"],
        "scene_count": row["scene_count"],
        "status": row["status"],
        "error_message": row["error_message"],
        "progress": row["progress"],
        "progress_label": row["progress_label"],
        "is_official": bool(row["is_official"]),
        "public": bool(row["public"]),
        "owner_user_id": row["owner_user_id"],
        "raw_meta": _json.loads(row["raw_meta"] or "{}"),
        "likes": row["likes"],
        "input_text": row["input_text"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def upsert_scene(s: dict) -> dict:
    """story_id + scene_index 是逻辑唯一。raw_json 存原始 scene.json 全量。"""
    story_id = s["story_id"]
    idx = int(s["scene_index"])
    sid = s.get("id") or f"{story_id}:{idx:03d}"
    raw = s.get("raw_json")
    if isinstance(raw, dict):
        raw = _json.dumps(raw, ensure_ascii=False)
    with _conn() as c:
        c.execute(
            """
            INSERT INTO scenes
                (id, story_id, scene_index, scene_type, title, narration,
                 interaction_goal, initial_frame, event_outcome,
                 comic_url, background_url, raw_json, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                scene_type = excluded.scene_type,
                title = excluded.title,
                narration = excluded.narration,
                interaction_goal = excluded.interaction_goal,
                initial_frame = excluded.initial_frame,
                event_outcome = excluded.event_outcome,
                comic_url = excluded.comic_url,
                background_url = excluded.background_url,
                raw_json = excluded.raw_json
            """,
            (
                sid, story_id, idx,
                s.get("scene_type", "narrative"),
                s.get("title", ""),
                s.get("narration", ""),
                s.get("interaction_goal"),
                s.get("initial_frame"),
                s.get("event_outcome"),
                s.get("comic_url"),
                s.get("background_url"),
                raw or "{}",
                int(s.get("created_at") or _now()),
            ),
        )
    return get_scene(story_id, idx) or {}


def get_scene(story_id: str, scene_index: int) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM scenes WHERE story_id = ? AND scene_index = ?",
            (story_id, scene_index),
        ).fetchone()
    if not row:
        return None
    return _row_to_scene(row)


def list_scenes(story_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM scenes WHERE story_id = ? ORDER BY scene_index ASC",
            (story_id,),
        ).fetchall()
    return [_row_to_scene(r) for r in rows]


def _row_to_scene(row) -> dict:
    return {
        "id": row["id"],
        "story_id": row["story_id"],
        "scene_index": row["scene_index"],
        "scene_type": row["scene_type"],
        "title": row["title"],
        "narration": row["narration"],
        "interaction_goal": row["interaction_goal"],
        "initial_frame": row["initial_frame"],
        "event_outcome": row["event_outcome"],
        "comic_url": row["comic_url"],
        "background_url": row["background_url"],
        "raw_json": _json.loads(row["raw_json"] or "{}"),
        "created_at": row["created_at"],
    }


def upsert_asset(a: dict) -> dict:
    """统一资产表：scope ∈ {global, scene, user}, kind ∈ {character, object}。"""
    aid = a.get("id") or ("a_" + secrets.token_hex(6))
    now = _now()
    with _conn() as c:
        c.execute(
            """
            INSERT INTO assets
                (id, name, kind, url, svg_url, description, scope,
                 story_id, scene_index, is_official, public, owner_user_id,
                 origin_story_id, origin_scene_idx, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                url = excluded.url,
                svg_url = excluded.svg_url,
                description = excluded.description,
                scope = excluded.scope,
                story_id = excluded.story_id,
                scene_index = excluded.scene_index,
                is_official = excluded.is_official,
                public = excluded.public
            """,
            (
                aid,
                a["name"],
                a.get("kind", "object"),
                a["url"],
                a.get("svg_url"),
                a.get("description", ""),
                a.get("scope", "user"),
                a.get("story_id"),
                a.get("scene_index"),
                1 if a.get("is_official") else 0,
                1 if a.get("public") else 0,
                a.get("owner_user_id"),
                a.get("origin_story_id"),
                a.get("origin_scene_idx"),
                int(a.get("created_at") or now),
            ),
        )
    return get_asset(aid) or {}


def get_asset(asset_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    return _row_to_asset(row) if row else None


def find_scene_asset(story_id: str, scene_index: int, name: str, kind: str) -> Optional[dict]:
    """优先 scene-local；找不到回落 global。"""
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM assets WHERE story_id = ? AND scene_index = ? AND name = ? AND kind = ? AND scope = 'scene'",
            (story_id, scene_index, name, kind),
        ).fetchone()
        if row:
            return _row_to_asset(row)
        row = c.execute(
            "SELECT * FROM assets WHERE story_id = ? AND name = ? AND kind = ? AND scope = 'global'",
            (story_id, name, kind),
        ).fetchone()
    return _row_to_asset(row) if row else None


def list_assets(*, owner_user_id: Optional[str] = None, scope: Optional[str] = None,
                story_id: Optional[str] = None, is_official: Optional[bool] = None,
                public: Optional[bool] = None) -> list[dict]:
    sql = "SELECT * FROM assets WHERE 1=1"
    args: list = []
    if owner_user_id is not None:
        sql += " AND owner_user_id = ?"; args.append(owner_user_id)
    if scope is not None:
        sql += " AND scope = ?"; args.append(scope)
    if story_id is not None:
        sql += " AND story_id = ?"; args.append(story_id)
    if is_official is not None:
        sql += " AND is_official = ?"; args.append(1 if is_official else 0)
    if public is not None:
        sql += " AND public = ?"; args.append(1 if public else 0)
    sql += " ORDER BY created_at DESC"
    with _conn() as c:
        rows = c.execute(sql, args).fetchall()
    return [_row_to_asset(r) for r in rows]


def assets_by_ids(ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    placeholders = ",".join(["?"] * len(ids))
    with _conn() as c:
        rows = c.execute(
            f"SELECT * FROM assets WHERE id IN ({placeholders})", ids,
        ).fetchall()
    return {r["id"]: _row_to_asset(r) for r in rows}


def delete_asset(asset_id: str, owner_user_id: Optional[str] = None) -> bool:
    sql = "DELETE FROM assets WHERE id = ?"
    args: list = [asset_id]
    if owner_user_id is not None:
        sql += " AND owner_user_id = ?"; args.append(owner_user_id)
    with _conn() as c:
        cur = c.execute(sql, args)
        return cur.rowcount > 0


def _row_to_asset(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "url": row["url"],
        "svg_url": row["svg_url"],
        "description": row["description"],
        "scope": row["scope"],
        "story_id": row["story_id"],
        "scene_index": row["scene_index"],
        "is_official": bool(row["is_official"]),
        "public": bool(row["public"]),
        "owner_user_id": row["owner_user_id"],
        "origin_story_id": row["origin_story_id"],
        "origin_scene_idx": row["origin_scene_idx"],
        "created_at": row["created_at"],
    }


# 启动时自动建表
init_db()
