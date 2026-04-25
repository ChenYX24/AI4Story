import json
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..db import (
    user_by_token,
    create_session,
    update_session,
    get_sessions_for_story,
    get_sessions_for_user,
    delete_session,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _require_user(authorization: Optional[str]) -> dict:
    token = (authorization or "").removeprefix("Bearer ").strip()
    u = user_by_token(token)
    if not u:
        raise HTTPException(401, "请先登录")
    return u


class CreateBody(BaseModel):
    story_id: str
    play_state: dict


class UpdateBody(BaseModel):
    play_state: dict
    status: Optional[str] = None


def _is_valid_play_state(payload: object) -> bool:
    """A real ‘playing’ session must carry a flow with >=2 nodes — otherwise the
    resume modal renders garbage like 第 1 / 1 页."""
    if not isinstance(payload, dict):
        return False
    flow = payload.get("flow")
    return isinstance(flow, list) and len(flow) > 1


@router.post("")
def api_create(body: CreateBody, authorization: Optional[str] = Header(None)):
    u = _require_user(authorization)
    if not _is_valid_play_state(body.play_state):
        raise HTTPException(status_code=422, detail="play_state.flow must contain at least 2 nodes")
    s = create_session(u["id"], body.story_id, json.dumps(body.play_state, ensure_ascii=False))
    return s


@router.put("/{session_id}")
def api_update(session_id: str, body: UpdateBody, authorization: Optional[str] = Header(None)):
    u = _require_user(authorization)
    if body.status not in {"finished"} and not _is_valid_play_state(body.play_state):
        raise HTTPException(status_code=422, detail="play_state.flow must contain at least 2 nodes")
    ok = update_session(session_id, u["id"],
                        json.dumps(body.play_state, ensure_ascii=False),
                        body.status)
    if not ok:
        raise HTTPException(404, "会话不存在")
    return {"ok": True}


@router.get("")
def api_list(story_id: Optional[str] = None, authorization: Optional[str] = Header(None)):
    u = _require_user(authorization)
    sessions = get_sessions_for_story(u["id"], story_id) if story_id else get_sessions_for_user(u["id"])
    return {"sessions": sessions}


@router.delete("/{session_id}")
def api_delete(session_id: str, authorization: Optional[str] = Header(None)):
    u = _require_user(authorization)
    ok = delete_session(session_id, u["id"])
    if not ok:
        raise HTTPException(404, "会话不存在")
    return {"ok": True}
