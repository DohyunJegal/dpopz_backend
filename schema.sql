-- DPOPz schema (SQLite, WAL)

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE sources (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    kind    TEXT NOT NULL CHECK (kind IN ('user', 'import')),
    weight  REAL,
    enabled INTEGER NOT NULL DEFAULT 1
);

INSERT INTO sources (name, kind) VALUES ('user', 'user');

CREATE TABLE charts (
    id               INTEGER PRIMARY KEY,
    zasa_id          TEXT NOT NULL,                 -- zasa 곡 id
    difficulty       TEXT NOT NULL CHECK (difficulty IN ('H', 'A', 'L')),
    title            TEXT NOT NULL,
    title_normalized TEXT NOT NULL,                 -- normalize_title(), 외부 데이터 매칭용
    level            INTEGER NOT NULL,              -- 공식 레벨 (☆N)
    lvx              REAL,                          -- 비공식 레벨 (N.x)
    version          TEXT,                          -- zasa 섹션명 (ex.'1st style')
    platform         TEXT NOT NULL DEFAULT 'AC',    -- INFINITAS 대비
    lvx_updated_at   TEXT,
    UNIQUE (zasa_id, difficulty)
);
CREATE INDEX charts_norm ON charts (title_normalized, difficulty);

CREATE TABLE chart_alias (
    alias_title TEXT NOT NULL,
    difficulty  TEXT NOT NULL,
    chart_id    INTEGER NOT NULL REFERENCES charts(id),
    PRIMARY KEY (alias_title, difficulty)
);

CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    login_id      TEXT NOT NULL UNIQUE COLLATE NOCASE,      -- 대소문자 미구별
    password_hash TEXT,                                     -- bcrypt
    iidx_id       TEXT UNIQUE,
    email         TEXT,
    star          REAL,                                     -- 신뢰도 계산용 레이팅
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'banned', 'legacy')),
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    approved_at   TEXT,
    CHECK (status = 'legacy' OR (password_hash IS NOT NULL AND iidx_id IS NOT NULL AND email IS NOT NULL))
);

-- 서버 세션(쿠키에는 토큰, DB에는 sha256 해시 저장), 차단/로그아웃 즉시 반영
CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);
CREATE INDEX sessions_user ON sessions (user_id);

CREATE TABLE rating_curve (
    star   REAL PRIMARY KEY,
    points REAL NOT NULL
);

CREATE TABLE votes (
    id        INTEGER PRIMARY KEY,
    chart_id  INTEGER NOT NULL REFERENCES charts(id),
    source_id INTEGER NOT NULL REFERENCES sources(id),
    user_id   INTEGER REFERENCES users(id),  -- import 는 NULL
    flip      INTEGER NOT NULL CHECK (flip IN (0, 1)),
    opt_1p    INTEGER NOT NULL CHECK (opt_1p BETWEEN 0 AND 4), -- 옵션 코드: 0 OFF, 1 MIRROR, 2 RANDOM,
    opt_2p    INTEGER NOT NULL CHECK (opt_2p BETWEEN 0 AND 4), --            3 R-RANDOM, 4 S-RANDOM
    comment   TEXT CHECK (comment IS NULL OR length(comment) <= 100),
    voted_at  TEXT NOT NULL DEFAULT (datetime('now')),
    status    TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected'))
);

CREATE UNIQUE INDEX votes_user_once ON votes (user_id, chart_id, flip, opt_1p, opt_2p)
    WHERE user_id IS NOT NULL;
CREATE INDEX votes_chart ON votes (chart_id, status);

-- 채보 매칭 실패 보관용
CREATE TABLE import_unmatched (
    id         INTEGER PRIMARY KEY,
    source_id  INTEGER NOT NULL REFERENCES sources(id),
    raw_title  TEXT,
    difficulty TEXT,
    reason     TEXT NOT NULL CHECK (reason IN ('not_found', 'ambiguous')),
    raw_row    TEXT,                         -- JSON
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 관리자 동기화 버튼 실행 기록
CREATE TABLE sync_runs (
    id           INTEGER PRIMARY KEY,
    kind         TEXT NOT NULL,              -- 'zasa'
    started_at   TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at  TEXT,
    status       TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ok', 'failed')),
    triggered_by INTEGER REFERENCES users(id),
    added        INTEGER,
    changed      INTEGER,
    error        TEXT
);

CREATE TABLE reports (
    id          INTEGER PRIMARY KEY,
    category    TEXT,
    page        TEXT,
    description TEXT NOT NULL,
    user_id     INTEGER REFERENCES users(id),       -- 비로그인 제보는 NULL
    resolved    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
