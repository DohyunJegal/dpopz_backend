import os
import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"
DB_PATH = os.environ.get("DPOPZ_DB", str(Path(__file__).resolve().parent.parent / "dpopz.db"))


def connect(path: str = DB_PATH) -> sqlite3.Connection:
    # isolation_level=None: 트랜잭션은 호출하는 쪽이 BEGIN/COMMIT으로 직접 제어
    # check_same_thread=False: FastAPI 가 의존성과 엔드포인트를 서로 다른 스레드에서 실행할 수 있음(연결은 요청마다 하나)
    conn = sqlite3.connect(path, isolation_level=None, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    """빈 DB에만 스키마를 적용"""
    has_tables = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone()
    if not has_tables:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
