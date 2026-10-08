"""계정 승인/차단, ★ 입력, zasa 동기화, 매칭 실패 목록 열람"""
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import auth, zasa
from app.db import get_db
from app.queries import DIFF_NAMES, option_names

router = APIRouter(prefix="/api/admin", dependencies=[Depends(auth.require_admin)])


class StarBody(BaseModel):
    star: float | None = Field(None, ge=0, le=20)


def _star(v):
    return None if v is None else round(v, 2)   # 변환표와 정확히 일치해야 pt 계산


def _changed(cur):
    if cur.rowcount == 0:
        raise HTTPException(409, "대상을 찾을 수 없거나 현재 상태에서는 할 수 없습니다.")
    return {"ok": True}


# ────────── 계정 ──────────
@router.get("/users")
def users(status: str | None = Query(None, pattern="^(pending|active|banned|legacy)$"), db=Depends(get_db)):
    sql = ("SELECT id, login_id, iidx_id, email, star, status, is_admin, created_at, approved_at "
           "FROM users" + (" WHERE status = ?" if status else "") + " ORDER BY id")
    return [dict(r) for r in db.execute(sql, (status,) if status else ())]


@router.post("/users/{user_id}/approve")
def approve(user_id: int, body: StarBody, db=Depends(get_db)):
    return _changed(db.execute(
        "UPDATE users SET status='active', star=?, approved_at=datetime('now') WHERE id=? AND status='pending'",
        (_star(body.star), user_id)))


@router.delete("/users/{user_id}")
def reject(user_id: int, db=Depends(get_db)):
    """승인 대기 신청 거절 (삭제). 같은 사람이 다시 신청할 수 있다."""
    return _changed(db.execute("DELETE FROM users WHERE id=? AND status='pending'", (user_id,)))


@router.post("/users/{user_id}/ban")
def ban(user_id: int, db=Depends(get_db)):
    res = _changed(db.execute(
        "UPDATE users SET status='banned' WHERE id=? AND status='active' AND is_admin=0", (user_id,)))
    db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    return res


@router.post("/users/{user_id}/unban")
def unban(user_id: int, db=Depends(get_db)):
    return _changed(db.execute("UPDATE users SET status='active' WHERE id=? AND status='banned'", (user_id,)))


@router.put("/users/{user_id}/star")
def set_star(user_id: int, body: StarBody, db=Depends(get_db)):
    """가명(legacy) 계정 포함 ★ 수정."""
    return _changed(db.execute("UPDATE users SET star=? WHERE id=?", (_star(body.star), user_id)))


# ────────── 투표 검수 ──────────
class ReviewBody(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    status: Literal["approved", "rejected"]


@router.get("/votes")
def votes(status: str = Query("pending", pattern="^(pending|approved|rejected)$"),
          limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db=Depends(get_db)):
    """사용자 투표 검수 목록"""
    total = db.execute("SELECT COUNT(*) FROM votes WHERE status = ? AND user_id IS NOT NULL", (status,)).fetchone()[0]
    rows = db.execute(
        """SELECT v.id, u.login_id AS author, c.title, c.difficulty, v.flip, v.opt_1p, v.opt_2p, v.comment,
                  v.voted_at, v.status
           FROM votes v JOIN users u ON u.id = v.user_id JOIN charts c ON c.id = v.chart_id
           WHERE v.status = ? ORDER BY v.id LIMIT ? OFFSET ?""", (status, limit, offset)).fetchall()
    return {"total": total, "items": [
        {"id": r["id"], "author": r["author"], "title": r["title"], "difficulty": DIFF_NAMES[r["difficulty"]],
         **option_names(r["flip"], r["opt_1p"], r["opt_2p"]), "comment": r["comment"],
         "voted_at": r["voted_at"], "status": r["status"]} for r in rows]}


@router.post("/votes/review")
def review_votes(body: ReviewBody, db=Depends(get_db)):
    """선택한 사용자 투표 승인/거절"""
    cur = db.execute(
        "UPDATE votes SET status = ? WHERE id IN (SELECT value FROM json_each(?)) AND user_id IS NOT NULL",
        (body.status, json.dumps(body.ids)))
    return {"updated": cur.rowcount}


# ────────── zasa 동기화 ──────────
@router.post("/sync/zasa")
def sync_zasa(admin=Depends(auth.require_admin), db=Depends(get_db)):
    try:
        return zasa.sync(db, triggered_by=admin["id"])
    except zasa.SyncBusy as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(502, f"zasa 동기화 실패: {e}")


@router.get("/sync/runs")
def sync_runs(db=Depends(get_db)):
    return [dict(r) for r in db.execute(
        """SELECT r.id, r.kind, r.started_at, r.finished_at, r.status, r.added, r.changed, r.error,
                  u.login_id AS triggered_by
           FROM sync_runs r LEFT JOIN users u ON u.id = r.triggered_by ORDER BY r.id DESC LIMIT 10""")]


# ────────── 매칭 실패 목록 ──────────
@router.get("/unmatched")
def unmatched(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db=Depends(get_db)):
    total = db.execute("SELECT COUNT(*) FROM import_unmatched").fetchone()[0]
    rows = db.execute(
        """SELECT m.id, s.name AS source, m.raw_title, m.difficulty, m.reason, m.created_at
           FROM import_unmatched m JOIN sources s ON s.id = m.source_id
           ORDER BY s.name, m.raw_title LIMIT ? OFFSET ?""", (limit, offset)).fetchall()
    return {"total": total, "items": [dict(r) for r in rows]}


# ────────── 오류 제보 ──────────
class ResolveBody(BaseModel):
    resolved: bool


@router.get("/reports")
def reports(resolved: bool = False, db=Depends(get_db)):
    return [dict(r) for r in db.execute(
        """SELECT r.id, r.category, r.page, r.description, r.resolved, r.created_at,
                  COALESCE(u.login_id, '(guest)') AS author
           FROM reports r LEFT JOIN users u ON u.id = r.user_id
           WHERE r.resolved = ? ORDER BY r.id DESC LIMIT 200""", (int(resolved),))]


@router.put("/reports/{report_id}")
def resolve_report(report_id: int, body: ResolveBody, db=Depends(get_db)):
    return _changed(db.execute("UPDATE reports SET resolved = ? WHERE id = ?", (int(body.resolved), report_id)))
