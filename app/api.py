from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app import queries
from app.db import get_db

router = APIRouter(prefix="/api")

# 로그인과 무관한 공개 데이터는 Vercel 엣지가 60초 캐시, 투표 반영은 최대 1분 지연
PUBLIC_CACHE = "public, s-maxage=60, stale-while-revalidate=300"


@router.get("/charts")
def charts(response: Response, q: str | None = None, level: int | None = None, version: str | None = None,
           sort: str = Query("title", pattern="^(title|lvx|level|version|diff)$"),
           order: str | None = Query(None, pattern="^(asc|desc)$"),
           limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db=Depends(get_db)):
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return queries.list_charts(db, q, level, version, limit, offset, sort, order)


@router.get("/charts/{chart_id}")
def chart(chart_id: int, response: Response, db=Depends(get_db)):
    response.headers["Cache-Control"] = PUBLIC_CACHE
    found = queries.get_chart(db, chart_id)
    if found is None:
        raise HTTPException(404, "채보를 찾을 수 없습니다.")
    return found


@router.get("/versions")
def versions(response: Response, db=Depends(get_db)):
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return queries.versions(db)
