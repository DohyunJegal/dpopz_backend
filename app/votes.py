"""투표 API. 관리자가 승인 후 집계 반영, 사용자가 취소/수정 불가"""
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app import auth
from app.db import get_db
from app.queries import DIFF_NAMES, OPT_NAMES, TRACKED_LEVELS, option_names

router = APIRouter(prefix="/api")

vote_limiter = auth.Limiter(60, 3600)   # 사용자당 시간당 60표

Option = Literal[tuple(OPT_NAMES)]      # OFF, MIRROR, RANDOM, R-RANDOM, S-RANDOM


class VoteBody(BaseModel):
    chart_id: int
    flip: Literal["OFF", "FLIP"] = "OFF"
    left: Option                            # 1P(LEFT)
    right: Option                           # 2P(RIGHT)
    comment: str | None = Field(None, max_length=100)

    @field_validator("comment")
    @classmethod
    def blank_is_none(cls, v):
        return (v.strip() or None) if v is not None else None


@router.post("/votes", status_code=201)
def create_vote(body: VoteBody, user=Depends(auth.require_user), db=Depends(get_db)):
    vote_limiter.check(user["id"])
    vote_limiter.hit(user["id"])
    chart = db.execute("SELECT level FROM charts WHERE id = ?", (body.chart_id,)).fetchone()
    if chart is None:
        raise HTTPException(404, "채보를 찾을 수 없습니다.")
    if chart["level"] not in TRACKED_LEVELS:
        raise HTTPException(400, "투표 대상이 아닌 채보입니다.")
    try:
        cur = db.execute(
            """INSERT INTO votes (chart_id, source_id, user_id, flip, opt_1p, opt_2p, comment)
               VALUES (?, (SELECT id FROM sources WHERE name = 'user'), ?, ?, ?, ?, ?)""",
            (body.chart_id, user["id"], int(body.flip == "FLIP"), OPT_NAMES.index(body.left),
             OPT_NAMES.index(body.right), body.comment))
    except sqlite3.IntegrityError:           # votes_user_once
        raise HTTPException(409, "이미 같은 옵션으로 투표했습니다.")
    return {"id": cur.lastrowid, "status": "pending"}


@router.get("/me/votes")
def my_votes(user=Depends(auth.require_user), db=Depends(get_db)):
    return [
        {"id": r["id"], "chart_id": r["chart_id"], "title": r["title"], "difficulty": DIFF_NAMES[r["difficulty"]],
         **option_names(r["flip"], r["opt_1p"], r["opt_2p"]),
         "comment": r["comment"], "voted_at": r["voted_at"], "status": r["status"]}
        for r in db.execute(
            """SELECT v.id, v.chart_id, c.title, c.difficulty, v.flip, v.opt_1p, v.opt_2p, v.comment, v.voted_at, v.status
               FROM votes v JOIN charts c ON c.id = v.chart_id
               WHERE v.user_id = ? ORDER BY v.id DESC LIMIT 500""", (user["id"],))]
