"""외부 데이터의 곡명과 DB 곡명 매칭. 실패 시  None과 reason 반환.

chart_alias와 normalize_title 일치 비교 후 후보가 둘 이상이면 'ambiguous' 처리
"""
import json
import logging

from app.titles import normalize_title

log = logging.getLogger("dpopz.match")


def match_chart(conn, title: str, difficulty: str):
    title = title.strip()
    alias = conn.execute(
        "SELECT chart_id FROM chart_alias WHERE alias_title=? AND difficulty=?", (title, difficulty)).fetchone()
    if alias:
        return alias[0], None
    norm = normalize_title(title)
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM charts WHERE title_normalized=? AND difficulty=?", (norm, difficulty))]
    if len(ids) == 1:
        return ids[0], None
    reason = "not_found" if not ids else "ambiguous"
    log.warning("Chart match failed | title=%s | normalized=%s | diff=%s | %s", title, norm, difficulty, reason)
    return None, reason


def record_unmatched(conn, source_id: int, title: str, difficulty: str, reason: str, raw_row) -> None:
    conn.execute(
        "INSERT INTO import_unmatched (source_id, raw_title, difficulty, reason, raw_row) VALUES (?,?,?,?,?)",
        (source_id, title, difficulty, reason, json.dumps(raw_row, ensure_ascii=False, default=str)))
