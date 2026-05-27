from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


@dataclass(frozen=True)
class ChatMessage:
    chat_id: int
    user_id: int
    username: str | None
    display_name: str
    text: str
    created_at: str

    @property
    def speaker(self) -> str:
        return self.username or self.display_name or str(self.user_id)


class Storage:
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
                    display_name TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_chat_created
                ON messages (chat_id, created_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_chat_user
                ON messages (chat_id, user_id)
                """
            )

    def save_message(
        self,
        chat_id: int,
        user_id: int,
        username: str | None,
        display_name: str,
        text: str,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (chat_id, user_id, username, display_name, text, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chat_id, user_id, username, display_name, text, created_at),
            )

    def recent_messages(self, chat_id: int, limit: int) -> list[ChatMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT chat_id, user_id, username, display_name, text, created_at
                FROM messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
        return [self._row_to_message(row) for row in reversed(rows)]

    def style_samples(self, chat_id: int, limit: int) -> list[ChatMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT chat_id, user_id, username, display_name, text, created_at
                FROM messages
                WHERE chat_id = ?
                  AND length(text) BETWEEN 3 AND 500
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
        return [self._row_to_message(row) for row in reversed(rows)]

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> ChatMessage:
        return ChatMessage(
            chat_id=row["chat_id"],
            user_id=row["user_id"],
            username=row["username"],
            display_name=row["display_name"],
            text=row["text"],
            created_at=row["created_at"],
        )
