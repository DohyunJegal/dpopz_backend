"""오류 제보. 비회원 전송 가능 (스팸 방지 IP당 시간당 5건)"""
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

from app import auth
from app.db import get_db

router = APIRouter(prefix="/api")

report_limiter = auth.Limiter(5, 3600)


class ReportBody(BaseModel):
    category: Literal["bug", "data", "ui", "other"]
    page: Literal["index", "table", "vote", "login", "signup", "mypage", "about", "other"] = "other"
    description: str = Field(min_length=1, max_length=1000)

    @field_validator("description")
    @classmethod
    def not_blank(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("내용을 입력해주세요.")
        return v


@router.post("/reports", status_code=201)
def create_report(body: ReportBody, request: Request, user=Depends(auth.current_user), db=Depends(get_db)):
    ip = request.client.host if request.client else "?"
    report_limiter.check(ip)
    report_limiter.hit(ip)
    db.execute("INSERT INTO reports (category, page, description, user_id) VALUES (?, ?, ?, ?)",
               (body.category, body.page, body.description, user["id"] if user else None))
    return {"ok": True}
