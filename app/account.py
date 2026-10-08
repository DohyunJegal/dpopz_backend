"""가입 신청 / 로그인 / 로그아웃 / 내 정보.  가입은 관리자가 승인해야 로그인 가능 (pending -> active)"""
import re
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from app import auth
from app.db import get_db

router = APIRouter(prefix="/api")

signup_limiter = auth.Limiter(5, 3600)      # IP 당 시간당 가입 신청 5회
login_limiter = auth.Limiter(5, 600)        # (IP, ID) 당 10분에 실패 5회
ip_login_limiter = auth.Limiter(30, 600)    # IP 당 10분에 실패 30회

_RESERVED = re.compile(r"^user\d+$", re.I)  # 가명 계정(user1, user2, ...) 충돌 방지


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


class SignupBody(BaseModel):
    login_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{4,20}$")
    password: str = Field(min_length=6, max_length=72)
    iidx_id: str = Field(pattern=r"^\d{8}$")
    email: str = Field(max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

    @field_validator("login_id")
    @classmethod
    def not_reserved(cls, v):
        if _RESERVED.match(v):
            raise ValueError("사용할 수 없는 ID입니다.")
        return v

    @field_validator("password")
    @classmethod
    def strong_enough(cls, v):
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("비밀번호는 영문과 숫자를 포함해야 합니다.")
        if len(v.encode()) > 72:    # bcrypt 한계
            raise ValueError("비밀번호가 너무 깁니다.")
        return v

    @field_validator("iidx_id", mode="before")
    @classmethod
    def strip_hyphen(cls, v):
        return v.replace("-", "") if isinstance(v, str) else v


class LoginBody(BaseModel):
    login_id: str = Field(max_length=64)
    password: str = Field(max_length=200)


@router.post("/signup", status_code=201)
def signup(body: SignupBody, request: Request, db=Depends(get_db)):
    ip = _ip(request)
    signup_limiter.check(ip)
    signup_limiter.hit(ip)
    try:
        db.execute("INSERT INTO users (login_id, password_hash, iidx_id, email) VALUES (?, ?, ?, ?)",
                   (body.login_id, auth.hash_password(body.password), body.iidx_id, body.email))
    except sqlite3.IntegrityError as e:
        if "login_id" in str(e):
            raise HTTPException(409, "이미 사용 중인 ID입니다.")
        if "iidx_id" in str(e):
            raise HTTPException(409, "이미 가입 신청된 IIDX ID입니다.")
        raise
    return {"status": "pending"}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db=Depends(get_db)):
    ip = _ip(request)
    key = (ip, body.login_id.lower())
    login_limiter.check(key)
    ip_login_limiter.check(ip)
    user = db.execute("SELECT * FROM users WHERE login_id = ? AND status != 'legacy'", (body.login_id,)).fetchone()
    if not auth.verify_password(body.password, user["password_hash"] if user else None):
        login_limiter.hit(key)
        ip_login_limiter.hit(ip)
        raise HTTPException(401, "ID 또는 비밀번호가 올바르지 않습니다.")
    if user["status"] == "pending":
        raise HTTPException(403, "관리자 승인 대기 중입니다.")
    if user["status"] == "banned":
        raise HTTPException(403, "이용이 제한된 계정입니다.")
    token = auth.create_session(db, user["id"])
    response.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_DAYS * 86400, httponly=True,
                        samesite="lax", secure=auth.COOKIE_SECURE, path="/")
    return {"login_id": user["login_id"], "is_admin": bool(user["is_admin"])}


@router.post("/logout")
def logout(request: Request, response: Response, db=Depends(get_db)):
    token = request.cookies.get(auth.COOKIE)
    if token:
        auth.delete_session(db, token)
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(auth.require_user)):
    return {"login_id": user["login_id"], "is_admin": bool(user["is_admin"])}
