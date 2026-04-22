from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..db import (
    AuthError,
    login_user,
    logout_token,
    register_user,
    user_by_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthRequest(BaseModel):
    nickname: str
    password: str


class AuthResponse(BaseModel):
    id: str
    nickname: str
    token: str


class MeResponse(BaseModel):
    id: str
    nickname: str
    created_at: int


def _extract_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


@router.post("/register", response_model=AuthResponse)
def register(req: AuthRequest):
    try:
        return register_user(req.nickname, req.password)
    except AuthError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=AuthResponse)
def login(req: AuthRequest):
    try:
        return login_user(req.nickname, req.password)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", response_model=MeResponse)
def me(authorization: Optional[str] = Header(default=None)):
    token = _extract_token(authorization)
    u = user_by_token(token)
    if not u:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return u


@router.post("/logout")
def logout(authorization: Optional[str] = Header(default=None)):
    token = _extract_token(authorization)
    logout_token(token)
    return {"ok": True}
