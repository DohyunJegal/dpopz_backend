"""zasa.sakura.ne.jp/dp/run.php 비공식 난이도표 동기화"""
import re
import sqlite3

import requests
from bs4 import BeautifulSoup

from app.titles import normalize_title

ZASA_URL = "https://zasa.sakura.ne.jp/dp/run.php"
DIFFICULTY = {"5": "H", "7": "A", "9": "L"}
CELL_RE = re.compile(r"☆(\d+)\s*\(([0-9.]+)\)")                 # ☆12 (12.1) → level, lvx
LINK_RE = re.compile(r"music\.php\?id=(\d{5})-([579])-[01]")    # zasa_id, 난이도 키

BUSY_MINUTES = 10   # 이 시간 안에 시작된 running 기록이 있으면 새 실행 거부
MIN_RATIO = 0.5     # 파싱 결과가 기존 채보 수의 절반 미만이면 페이지 구조 변경으로 보고 중단


class SyncBusy(Exception):
    pass


def _parse_cell(cell):
    a = cell.find("a")
    if not a:
        return None
    link = LINK_RE.search(a.get("href", ""))
    num = CELL_RE.search(a.get_text())
    if not link or not num:
        return None
    return link.group(1), DIFFICULTY[link.group(2)], int(num.group(1)), float(num.group(2))


def parse(html: str) -> list[dict]:
    charts, version = [], None
    for row in BeautifulSoup(html, "html.parser").find_all("tr"):
        th = row.find("th")
        if th:
            version = th.get_text(strip=True)
            continue
        cells = row.find_all("td")
        if len(cells) < 4:
            continue    # 열 구성: H | A | L | 곡명
        title = cells[-1].get_text(strip=True)
        if not title:
            continue
        for cell in cells[:3]:
            parsed = _parse_cell(cell)
            if parsed:
                zasa_id, diff, level, lvx = parsed
                charts.append(dict(zasa_id=zasa_id, difficulty=diff, title=title,
                                   level=level, lvx=lvx, version=version))
    return charts


def fetch() -> str:
    resp = requests.get(ZASA_URL, timeout=30, headers={"User-Agent": "DPOPz-sync"})
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text


def sync(conn: sqlite3.Connection, html: str | None = None, triggered_by: int | None = None) -> dict:
    # 동시 클릭 방지를 위해 실행 중 확인과 기록 생성을 한 번에 처리
    conn.execute("BEGIN IMMEDIATE")
    busy = conn.execute(
        "SELECT 1 FROM sync_runs WHERE kind='zasa' AND status='running' "
        "AND started_at > datetime('now', ?)", (f"-{BUSY_MINUTES} minutes",)).fetchone()
    if busy:
        conn.execute("ROLLBACK")
        raise SyncBusy("이미 동기화가 실행 중입니다.")
    run_id = conn.execute(
        "INSERT INTO sync_runs (kind, triggered_by) VALUES ('zasa', ?)", (triggered_by,)).lastrowid
    conn.execute("COMMIT")

    try:
        charts = parse(html if html is not None else fetch())
        existing = conn.execute("SELECT COUNT(*) FROM charts").fetchone()[0]
        if not charts or len(charts) < existing * MIN_RATIO:
            raise ValueError(f"파싱 결과가 비정상입니다 ({len(charts)}개, 기존 {existing}개). 페이지 구조가 변경되었는지 확인하세요.")

        added = changed = 0
        conn.execute("BEGIN")
        for c in charts:
            old = conn.execute(
                "SELECT title, level, lvx, version FROM charts WHERE zasa_id=? AND difficulty=?",
                (c["zasa_id"], c["difficulty"])).fetchone()
            norm = normalize_title(c["title"])
            if old is None:
                conn.execute(
                    "INSERT INTO charts (zasa_id, difficulty, title, title_normalized, level, lvx, version, lvx_updated_at) "
                    "VALUES (?,?,?,?,?,?,?, datetime('now'))",
                    (c["zasa_id"], c["difficulty"], c["title"], norm, c["level"], c["lvx"], c["version"]))
                added += 1
            elif (old["title"], old["level"], old["lvx"], old["version"]) != (c["title"], c["level"], c["lvx"], c["version"]):
                conn.execute(
                    "UPDATE charts SET title=?, title_normalized=?, level=?, lvx=?, version=?, "
                    "lvx_updated_at = CASE WHEN lvx IS ? THEN lvx_updated_at ELSE datetime('now') END "
                    "WHERE zasa_id=? AND difficulty=?",
                    (c["title"], norm, c["level"], c["lvx"], c["version"], c["lvx"], c["zasa_id"], c["difficulty"]))
                changed += 1
        conn.execute("COMMIT")
    except Exception as e:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        conn.execute("UPDATE sync_runs SET status='failed', finished_at=datetime('now'), error=? WHERE id=?",
                     (str(e), run_id))
        raise

    conn.execute("UPDATE sync_runs SET status='ok', finished_at=datetime('now'), added=?, changed=? WHERE id=?",
                 (added, changed, run_id))
    return {"run_id": run_id, "parsed": len(charts), "added": added, "changed": changed}


if __name__ == "__main__":
    from app.db import connect, init_db
    db = connect()
    init_db(db)
    print(sync(db))
