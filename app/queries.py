"""옵션 조회 쿼리

pt 규칙:
  - 사용자 투표: rating_curve 값, 없으면 1pt
  - 외부 데이터: sources.weight, 없으면 0pt
  - 옵션 조합의 pt = 그 조합에 투표한 사람들의 pt 합, pt가 없으면 None

정렬: pt 내림차순, 같으면 득표 수
"""
import json

from app.titles import normalize_title

OPT_NAMES = ["OFF", "MIRROR", "RANDOM", "R-RANDOM", "S-RANDOM"]
TRACKED_LEVELS = (11, 12)
DIFF_NAMES = {"H": "HYPER", "A": "ANOTHER", "L": "LEGGENDARIA"}

_WEIGHT = """CASE WHEN v.user_id IS NOT NULL THEN
                 CASE WHEN u.star IS NULL THEN NULL
                      ELSE COALESCE((SELECT points FROM rating_curve WHERE star = ROUND(u.star, 2)), 1.0) END
            ELSE s.weight END"""

_APPROVED = "v.status = 'approved' AND s.enabled = 1"


def option_names(flip, opt_1p, opt_2p):
    return {"flip": "FLIP" if flip else "OFF", "left": OPT_NAMES[opt_1p], "right": OPT_NAMES[opt_2p]}


def distributions(conn, chart_ids: list[int]) -> dict[int, list[dict]]:
    """옵션 조합 목록"""
    if not chart_ids:
        return {}
    rows = conn.execute(
        f"""SELECT v.chart_id, v.flip, v.opt_1p, v.opt_2p, COUNT(*) AS n, SUM({_WEIGHT}) AS pt
            FROM votes v JOIN sources s ON s.id = v.source_id LEFT JOIN users u ON u.id = v.user_id
            WHERE {_APPROVED} AND v.chart_id IN (SELECT value FROM json_each(?))
            GROUP BY v.chart_id, v.flip, v.opt_1p, v.opt_2p""",
        (json.dumps(chart_ids),)).fetchall()
    out: dict[int, list[dict]] = {cid: [] for cid in chart_ids}
    for r in rows:
        out[r["chart_id"]].append({**option_names(r["flip"], r["opt_1p"], r["opt_2p"]),
                                   "count": r["n"], "pt": None if r["pt"] is None else round(r["pt"], 1)})
    for combos in out.values():
        combos.sort(key=lambda d: (d["pt"] if d["pt"] is not None else -1, d["count"]), reverse=True)
        for rank, d in enumerate(combos, 1):
            d["rank"] = rank
    return out


def _chart_dict(r, options):
    return {"id": r["id"], "title": r["title"], "difficulty": DIFF_NAMES[r["difficulty"]], "level": r["level"],
            "lvx": r["lvx"], "version": r["version"], "votes": sum(o["count"] for o in options), "options": options}


# 정렬 열
SORTS = {
    "title": "title_normalized",
    "lvx": "lvx",
    "level": "level",
    "version": "zasa_id",
    "diff": "CASE difficulty WHEN 'H' THEN 0 WHEN 'A' THEN 1 ELSE 2 END",
}
DEFAULT_ORDER = {"title": "asc", "lvx": "desc", "level": "desc", "version": "asc", "diff": "asc"}


def list_charts(conn, q=None, level=None, version=None, limit=50, offset=0, sort="title", order=None) -> dict:
    direction = "DESC" if (order or DEFAULT_ORDER[sort]) == "desc" else "ASC"
    where, args = [], []
    if level is not None:
        where.append("level = ?"); args.append(level)
    else:
        where.append(f"level IN ({','.join('?' * len(TRACKED_LEVELS))})"); args += TRACKED_LEVELS
    if version:
        where.append("version = ?"); args.append(version)
    if q and normalize_title(q):
        where.append("title_normalized LIKE ?"); args.append(f"%{normalize_title(q)}%")
    sql_where = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM charts WHERE {sql_where}", args).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM charts WHERE {sql_where} "
        f"ORDER BY {SORTS[sort]} {direction}, title_normalized, difficulty LIMIT ? OFFSET ?",
        [*args, limit, offset]).fetchall()
    dist = distributions(conn, [r["id"] for r in rows])
    return {"total": total, "items": [_chart_dict(r, dist[r["id"]]) for r in rows]}


def get_chart(conn, chart_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM charts WHERE id = ?", (chart_id,)).fetchone()
    if r is None:
        return None
    chart = _chart_dict(r, distributions(conn, [chart_id])[chart_id])
    chart["comments"] = [
        {**option_names(c["flip"], c["opt_1p"], c["opt_2p"]), "comment": c["comment"]}
        for c in conn.execute(
            f"""SELECT v.flip, v.opt_1p, v.opt_2p, v.comment
                FROM votes v JOIN sources s ON s.id = v.source_id
                WHERE v.chart_id = ? AND {_APPROVED} AND v.comment IS NOT NULL
                ORDER BY v.voted_at, v.id""", (chart_id,))]
    return chart


def versions(conn) -> list[str]:
    """버전 목록"""
    return [r[0] for r in conn.execute(
        f"""SELECT version FROM charts WHERE level IN ({','.join('?' * len(TRACKED_LEVELS))}) AND version IS NOT NULL
            GROUP BY version ORDER BY MIN(zasa_id)""", TRACKED_LEVELS)]
