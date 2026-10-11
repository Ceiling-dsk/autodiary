import sqlite3
import time
from pathlib import Path

from .lifeday import life_day
from .parse import Conversation

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id               TEXT PRIMARY KEY,
    title            TEXT,
    create_time      REAL,
    update_time      REAL,
    deleted_upstream INTEGER NOT NULL DEFAULT 0,
    last_seen_at     REAL,
    project          TEXT,
    remote_update_time REAL
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    parent_id       TEXT,
    role            TEXT NOT NULL,
    content_type    TEXT,
    text            TEXT,
    create_time     REAL,
    life_day        TEXT,
    model           TEXT,
    on_main_branch  INTEGER NOT NULL,
    hidden          INTEGER NOT NULL,
    raw_json        TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_life_day ON messages(life_day);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    text, content='messages', content_rowid='rowid', tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE OF text ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    INSERT INTO messages_fts(rowid, text) VALUES (new.rowid, new.text);
END;
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    # 旧库补列
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(conversations)")}
    for col, typ in (("project", "TEXT"), ("remote_update_time", "REAL")):
        if col not in cols:
            conn.execute(f"ALTER TABLE conversations ADD COLUMN {col} {typ}")
    return conn


def remote_update_times(conn: sqlite3.Connection) -> dict[str, float]:
    """上次抓取时列表接口给出的 update_time，用来判断对话是否有变化。"""
    return {r["id"]: r["remote_update_time"] for r in conn.execute(
        "SELECT id, remote_update_time FROM conversations WHERE remote_update_time IS NOT NULL")}


def mark_fetched(conn: sqlite3.Connection, conv_id: str, project: str | None,
                 remote_update_time: float | None):
    with conn:
        conn.execute("UPDATE conversations SET project=?, remote_update_time=? WHERE id=?",
                     (project, remote_update_time, conv_id))


def upsert_conversation(conn: sqlite3.Connection, conv: Conversation) -> int:
    """幂等写入：同一 message_id 重复导入只会更新，不会重复。返回写入的消息数。"""
    with conn:
        conn.execute(
            """INSERT INTO conversations (id, title, create_time, update_time, last_seen_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title, update_time=excluded.update_time,
                 last_seen_at=excluded.last_seen_at, deleted_upstream=0""",
            (conv.id, conv.title, conv.create_time, conv.update_time, time.time()),
        )
        # 主线可能因编辑/重新生成而改变，先整体清零再按本次结果标记
        conn.execute("UPDATE messages SET on_main_branch=0 WHERE conversation_id=?", (conv.id,))
        for m in conv.messages:
            conn.execute(
                """INSERT INTO messages (id, conversation_id, parent_id, role, content_type, text,
                                         create_time, life_day, model, on_main_branch, hidden, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     text=excluded.text, content_type=excluded.content_type,
                     on_main_branch=excluded.on_main_branch, hidden=excluded.hidden,
                     raw_json=excluded.raw_json""",
                (m.id, m.conversation_id, m.parent_id, m.role, m.content_type, m.text,
                 m.create_time, life_day(m.create_time) if m.create_time else None,
                 m.model, int(m.on_main_branch), int(m.hidden), m.raw_json),
            )
    return len(conv.messages)


def set_projects(conn: sqlite3.Connection, projects: dict[str, str | None]):
    """对话可能被移入/移出项目，每次列表后同步已有对话的项目名。"""
    with conn:
        conn.executemany("UPDATE conversations SET project=? WHERE id=?",
                         [(proj, cid) for cid, proj in projects.items()])
