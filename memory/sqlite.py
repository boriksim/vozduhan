from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any


@dataclass(frozen=True)
class ChatMessage:
    id: int
    chat_id: int
    user_id: int
    username: str | None
    display_name: str
    text: str
    timestamp: str
    is_bot: bool = False

    @property
    def speaker(self) -> str:
        if self.username:
            return self.username
        return self.display_name or str(self.user_id)


@dataclass(frozen=True)
class UserProfile:
    user_id: int
    username: str | None
    profile_text: str
    message_count: int


@dataclass(frozen=True)
class ChatState:
    chat_id: int
    mood: float
    irritation: float
    engagement: float


class SQLiteMemory:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    display_name TEXT NOT NULL DEFAULT '',
                    text TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    is_bot INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._migrate_messages_table(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    profile_text TEXT NOT NULL DEFAULT '',
                    message_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state (
                    chat_id INTEGER PRIMARY KEY,
                    mood REAL NOT NULL DEFAULT 0,
                    irritation REAL NOT NULL DEFAULT 0,
                    engagement REAL NOT NULL DEFAULT 0.5,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_control (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    enabled INTEGER NOT NULL DEFAULT 1,
                    intervention_mode INTEGER NOT NULL DEFAULT 1,
                    last_response_at TEXT,
                    last_response_chat_id INTEGER,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_chat_id_id
                ON messages (chat_id, id)
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO bot_control
                (id, enabled, intervention_mode, updated_at)
                VALUES (1, 1, 1, ?)
                """,
                (self._now(),),
            )

    def _migrate_messages_table(self, conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "display_name" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
        if "timestamp" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN timestamp TEXT")
            if "created_at" in columns:
                conn.execute("UPDATE messages SET timestamp = created_at WHERE timestamp IS NULL")
        if "is_bot" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN is_bot INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            "UPDATE messages SET timestamp = ? WHERE timestamp IS NULL OR timestamp = ''",
            (self._now(),),
        )

    def save_message(
        self,
        chat_id: int,
        user_id: int,
        username: str | None,
        display_name: str,
        text: str,
        is_bot: bool = False,
    ) -> int:
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO messages
                (chat_id, user_id, username, display_name, text, timestamp, is_bot)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (chat_id, user_id, username, display_name, text, now, int(is_bot)),
            )
            if not is_bot:
                conn.execute(
                    """
                    INSERT INTO users (user_id, username, profile_text, message_count, updated_at)
                    VALUES (?, ?, '', 1, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = excluded.username,
                        message_count = users.message_count + 1,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, username, now),
                )
            return int(cursor.lastrowid)

    def recent_messages(self, chat_id: int, limit: int = 30) -> list[ChatMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, chat_id, user_id, username, display_name, text, timestamp, is_bot
                FROM messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
        return [self._row_to_message(row) for row in reversed(rows)]

    def recent_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, chat_id, user_id, username, display_name, text, timestamp, is_bot
                FROM messages
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_user_profile(self, user_id: int) -> UserProfile | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, profile_text, message_count FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        return UserProfile(
            user_id=row["user_id"],
            username=row["username"],
            profile_text=row["profile_text"],
            message_count=row["message_count"],
        )

    def update_user_profile(self, user_id: int, username: str | None, profile_text: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (user_id, username, profile_text, message_count, updated_at)
                VALUES (?, ?, ?, 0, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    profile_text = excluded.profile_text,
                    updated_at = excluded.updated_at
                """,
                (user_id, username, profile_text, self._now()),
            )

    def get_state(self, chat_id: int) -> ChatState:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO state
                (chat_id, mood, irritation, engagement, updated_at)
                VALUES (?, 0, 0, 0.5, ?)
                """,
                (chat_id, now),
            )
            row = conn.execute(
                "SELECT chat_id, mood, irritation, engagement FROM state WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return ChatState(row["chat_id"], row["mood"], row["irritation"], row["engagement"])

    def update_state(self, chat_id: int, mood: float, irritation: float, engagement: float) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO state (chat_id, mood, irritation, engagement, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    mood = excluded.mood,
                    irritation = excluded.irritation,
                    engagement = excluded.engagement,
                    updated_at = excluded.updated_at
                """,
                (chat_id, self._clamp(mood, -1, 1), self._clamp(irritation, 0, 1), self._clamp(engagement, 0, 1), self._now()),
            )

    def get_control(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT enabled, intervention_mode, last_response_at, last_response_chat_id
                FROM bot_control
                WHERE id = 1
                """
            ).fetchone()
        return dict(row)

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        return self._update_control("enabled", enabled)

    def set_intervention_mode(self, enabled: bool) -> dict[str, Any]:
        return self._update_control("intervention_mode", enabled)

    def mark_bot_response(self, chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE bot_control
                SET last_response_at = ?, last_response_chat_id = ?, updated_at = ?
                WHERE id = 1
                """,
                (self._now(), chat_id, self._now()),
            )

    def all_states(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT chat_id, mood, irritation, engagement, updated_at FROM state ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def _update_control(self, column: str, enabled: bool) -> dict[str, Any]:
        if column not in {"enabled", "intervention_mode"}:
            raise ValueError("invalid control column")
        with self._connect() as conn:
            conn.execute(
                f"UPDATE bot_control SET {column} = ?, updated_at = ? WHERE id = 1",
                (int(enabled), self._now()),
            )
        return self.get_control()

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> ChatMessage:
        return ChatMessage(
            id=row["id"],
            chat_id=row["chat_id"],
            user_id=row["user_id"],
            username=row["username"],
            display_name=row["display_name"],
            text=row["text"],
            timestamp=row["timestamp"],
            is_bot=bool(row["is_bot"]),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))
