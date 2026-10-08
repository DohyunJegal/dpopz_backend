"""비밀번호(bcrypt), 서버 세션, 로그인 시도 제한, 권한 의존성.

환경변수
  DPOPZ_BCRYPT_ROUNDS   기본 12
  DPOPZ_COOKIE_SECURE   '1' 이면 Secure 쿠키 (HTTPS 운영 시 켤 것)
"""
import hashlib
import os
import secrets
import time

import bcrypt
from fastapi import Depends, HTTPException, Request

from app.db import get_db

COOKIE = "dpopz_session"
SESSION_DAYS = 14
BCRYPT_ROUNDS = int(os.environ.get("DPOPZ_BCRYPT_ROUNDS", "12"))
COOKIE_SECURE = os.environ.get("DPOPZ_COOKIE_SECURE", "0") == "1"

# 없는 계정으로 로그인해도 같은 시간이 걸리게 (계정 존재 여부 노출 방지)
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt(BCRYPT_ROUNDS)).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()


def verify_password(password: str, hashed: str | None) -> bool:
    raw = password.encode()
    if hashed is None or len(raw) > 72:          # bcrypt 는 72바이트까지만 지원
        bcrypt.checkpw(b"dummy", _DUMMY_HASH.encode())
        return False
    return bcrypt.checkpw(raw, hashed.encode())


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db, user_id: int) -> str:
    db.execute("DELETE FROM sessions WHERE expires_at < datetime('now')")
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, datetime('now', ?))",
               (_digest(token), user_id, f"+{SESSION_DAYS} days"))
    return token


def delete_session(db, token: str) -> None:
    db.execute("DELETE FROM sessions WHERE token_hash = ?", (_digest(token),))


class Limiter:
    """프로세스 메모리 기반 시도 제한 (워커가 여러 개면 워커별로 센다)."""

    def __init__(self, attempts: int, seconds: int):
        self.attempts, self.seconds, self.hits = attempts, seconds, {}

    def _recent(self, key):
        now = time.monotonic()
        recent = [t for t in self.hits.get(key, []) if now - t < self.seconds]
        self.hits[key] = recent
        return recent

    def check(self, key) -> None:
        if len(self._recent(key)) >= self.attempts:
            raise HTTPException(429, "시도 횟수가 너무 많습니다. 잠시 후 다시 시도해주세요.")

    def hit(self, key) -> None:
        self._recent(key).append(time.monotonic())


def current_user(request: Request, db=Depends(get_db)):
    """로그인한 active 사용자 또는 None. 차단/만료 세션은 즉시 None."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    return db.execute(
        """SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token_hash = ? AND s.expires_at > datetime('now') AND u.status = 'active'""",
        (_digest(token),)).fetchone()


def require_user(user=Depends(current_user)):
    if user is None:
        raise HTTPException(401, "로그인이 필요합니다.")
    return user


def require_admin(user=Depends(require_user)):
    if not user["is_admin"]:
        raise HTTPException(403, "관리자 권한이 필요합니다.")
    return user
