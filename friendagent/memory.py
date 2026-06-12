"""Persistent memory: conversation history + long-term facts, in SQLite.

Two tables:
  messages  — full conversation log per person (used to rebuild context)
  facts     — durable key/value facts the companion has learned about her,
              surfaced into the system prompt so she feels remembered.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class Message:
    role: str  # "user" or "assistant"
    content: str
    ts: float


class Memory:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                ts REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_user_ts
                ON messages(user_id, ts);

            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                ts REAL NOT NULL,
                UNIQUE(user_id, key)
            );

            CREATE TABLE IF NOT EXISTS state (
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (user_id, key)
            );

            CREATE TABLE IF NOT EXISTS followups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                due_ts REAL NOT NULL,
                created_ts REAL NOT NULL,
                done INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_followups_due
                ON followups(done, due_ts);

            CREATE TABLE IF NOT EXISTS pending_sends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                due_ts REAL NOT NULL,
                payload TEXT NOT NULL,
                created_ts REAL NOT NULL,
                done INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_pending_due
                ON pending_sends(done, due_ts);
            """
        )
        self._conn.commit()

    # ---- messages -------------------------------------------------------
    def add_message(self, user_id: str, role: str, content: str) -> None:
        self._conn.execute(
            "INSERT INTO messages (user_id, role, content, ts) VALUES (?, ?, ?, ?)",
            (user_id, role, content, time.time()),
        )
        self._conn.commit()

    def recent_messages(self, user_id: str, limit: int = 20) -> list[Message]:
        rows = self._conn.execute(
            "SELECT role, content, ts FROM messages WHERE user_id = ? "
            "ORDER BY ts DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [Message(r["role"], r["content"], r["ts"]) for r in reversed(rows)]

    def message_count(self, user_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE user_id = ?", (user_id,)
        ).fetchone()
        return int(row["c"])

    # ---- facts ----------------------------------------------------------
    def upsert_fact(self, user_id: str, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO facts (user_id, key, value, ts) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, ts=excluded.ts",
            (user_id, key, value, time.time()),
        )
        self._conn.commit()

    def get_facts(self, user_id: str) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT key, value FROM facts WHERE user_id = ? ORDER BY ts", (user_id,)
        ).fetchall()
        return {r["key"]: r["value"] for r in rows}

    def facts_summary(self, user_id: str) -> str:
        facts = self.get_facts(user_id)
        if not facts:
            return ""
        return "\n".join(f"- {k}: {v}" for k, v in facts.items())

    # ---- misc state -----------------------------------------------------
    def set_state(self, user_id: str, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO state (user_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value",
            (user_id, key, value),
        )
        self._conn.commit()

    def get_state(self, user_id: str, key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM state WHERE user_id = ? AND key = ?", (user_id, key)
        ).fetchone()
        return row["value"] if row else None

    # ---- follow-ups -----------------------------------------------------
    def add_followup(self, user_id: str, topic: str, due_ts: float) -> None:
        now = time.time()
        self._conn.execute(
            "INSERT INTO followups (user_id, topic, due_ts, created_ts, done) "
            "VALUES (?, ?, ?, ?, 0)",
            (user_id, topic, due_ts, now),
        )
        self._conn.commit()

    def due_followups(self, now_ts: Optional[float] = None) -> list[tuple[int, str, str]]:
        """Return (id, user_id, topic) for follow-ups whose time has come."""
        now_ts = now_ts if now_ts is not None else time.time()
        rows = self._conn.execute(
            "SELECT id, user_id, topic FROM followups WHERE done = 0 AND due_ts <= ? "
            "ORDER BY due_ts",
            (now_ts,),
        ).fetchall()
        return [(r["id"], r["user_id"], r["topic"]) for r in rows]

    def mark_followup_done(self, followup_id: int) -> None:
        self._conn.execute(
            "UPDATE followups SET done = 1 WHERE id = ?", (followup_id,)
        )
        self._conn.commit()

    # ---- pending sends (durable, restart-safe delivery queue) -----------
    def enqueue_send(self, user_id: str, due_ts: float, payload: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO pending_sends (user_id, due_ts, payload, created_ts, done) "
            "VALUES (?, ?, ?, ?, 0)",
            (user_id, due_ts, payload, time.time()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def due_sends(self, now_ts: Optional[float] = None) -> list[tuple[int, str, str]]:
        now_ts = now_ts if now_ts is not None else time.time()
        rows = self._conn.execute(
            "SELECT id, user_id, payload FROM pending_sends "
            "WHERE done = 0 AND due_ts <= ? ORDER BY due_ts",
            (now_ts,),
        ).fetchall()
        return [(r["id"], r["user_id"], r["payload"]) for r in rows]

    def claim_send(self, send_id: int) -> bool:
        """Atomically claim a pending send. Returns True if WE got it.

        Prevents the in-process fast path and the scheduler backstop from both
        delivering the same message.
        """
        cur = self._conn.execute(
            "UPDATE pending_sends SET done = 1 WHERE id = ? AND done = 0", (send_id,)
        )
        self._conn.commit()
        return cur.rowcount == 1

    def known_user_ids(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT user_id FROM messages"
        ).fetchall()
        return [r["user_id"] for r in rows]

    def close(self) -> None:
        self._conn.close()
