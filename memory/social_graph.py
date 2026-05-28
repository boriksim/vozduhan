from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

logger = logging.getLogger(__name__)

CONFLICT_RE = re.compile(
    r"\b(спор|срач|конфликт|руга|оскорб|токсич|ненавиж|достал|задолбал|бред|идиот|дурак|тупой|заткнись|пошел|пошёл|хер|говно|клоун|ничтож)\b",
    re.IGNORECASE,
)

JOKE_RE = re.compile(
    r"\b(лол|ахах|хаха|кек|прикол|шутк|смешн|хохм|угар|ахаха)\b",
    re.IGNORECASE,
)

TOPIC_MARKER_RE = re.compile(
    r"(?:про\s+|об\s+|о\s+|насчёт\s+|на счёт\s+)(\w{4,})",
    re.IGNORECASE,
)


@dataclass
class SocialEdge:
    source_type: str
    source_id: int
    target_type: str
    target_id: int
    edge_type: str
    weight: float
    context_tag: str
    last_interaction: str


@dataclass
class SocialEvent:
    event_id: int
    event_type: str
    description: str
    involved_users: list[int]
    chat_id: int
    impact_score: float
    created_at: str
    resolved: bool


class SocialGraph:
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
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    source_id INTEGER NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id INTEGER NOT NULL,
                    edge_type TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 0.0,
                    context_tag TEXT DEFAULT '',
                    last_interaction TEXT NOT NULL,
                    UNIQUE(source_type, source_id, target_type, target_id, edge_type)
                );

                CREATE TABLE IF NOT EXISTS graph_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    involved_users TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    impact_score REAL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    resolved INTEGER DEFAULT 0
                );
            """)

    # ─── public API ────────────────────────────────────────────────

    def update_after_message(
        self,
        chat_id: int,
        user_id: int,
        username: str | None,
        text: str,
        is_bot: bool = False,
        bot_id: int | None = None,
    ) -> None:
        if is_bot:
            return

        now = self._now()
        tags: list[str] = []
        is_conflict = bool(CONFLICT_RE.search(text))
        is_joke = bool(JOKE_RE.search(text))

        # ── detect topics ──
        topics = self._extract_topics(text)
        for topic in topics:
            self._update_topic_edge(user_id, topic, 0.05, "interest_level", now)

        # ── update user ↔ bot edges ──
        self._update_edge("user", user_id, "bot", bot_id or 0, "familiarity", 0.02, now)
        if is_joke:
            self._update_edge("user", user_id, "bot", bot_id or 0, "humor_sync", 0.05, now)
        if is_conflict:
            self._update_edge("user", user_id, "bot", bot_id or 0, "annoyance", 0.06, now)

        # ── update user ↔ user edges (last N messages) ──
        other_users = self._recent_users(chat_id, user_id, limit=8)
        for other_id in other_users:
            self._update_edge("user", user_id, "user", other_id, "banter", 0.01, now)
            if is_conflict:
                self._update_edge("user", user_id, "user", other_id, "conflict", 0.04, now, "argument")

        # ── record events ──
        if is_conflict:
            self._record_event(
                event_type="conflict",
                description=text[:150],
                involved_users=[user_id] + other_users[:3],
                chat_id=chat_id,
                impact_score=0.6 if "идиот" in text.lower() or "пошел" in text.lower() else 0.4,
                now=now,
            )

    def get_user_context(self, user_id: int, chat_id: int, bot_id: int | None = None) -> str:
        lines: list[str] = []

        # user ↔ bot relationship (top 3)
        bot_edges = self._get_edges("user", user_id, "bot", bot_id or 0)
        for edge in bot_edges[:3]:
            symbol = self._weight_symbol(edge.weight)
            lines.append(f"  bot ↔ you [{edge.edge_type}] {symbol}")

        # user ↔ user relationships (top 3 strongest)
        user_edges = self._get_edges("user", user_id, "user", None)
        user_edges.sort(key=lambda e: abs(e.weight), reverse=True)
        for edge in user_edges[:3]:
            other_name = self._resolve_username(edge.target_id)
            symbol = self._weight_symbol(edge.weight)
            tag = f" ({edge.context_tag})" if edge.context_tag else ""
            lines.append(f"  you ↔ @{other_name} [{edge.edge_type}] {symbol}{tag}")

        # unresolved conflicts involving this user
        conflicts = self._get_active_events("conflict", chat_id, user_id)
        for ev in conflicts[:2]:
            lines.append(f"  ⚠ conflict: {ev.description[:80]}")

        # shared humor
        humor = [e for e in bot_edges if e.edge_type == "humor_sync"]
        if humor and humor[0].weight > 0.2:
            lines.append(f"  😏 humor sync: we share jokes")

        if not lines:
            return ""

        return "[SOCIAL GRAPH CONTEXT]\n" + "\n".join(lines) + "\n"

    def get_scoring_modifier(self, user_id: int, chat_id: int, bot_id: int | None = None) -> int:
        bonus = 0

        # strong conflict edge → +20
        conflict_edges = self._get_edges("user", user_id, "user", None, "conflict")
        if any(e.weight > 0.4 for e in conflict_edges):
            bonus += 20

        # high humor_sync → +15
        humor = self._get_edges("user", user_id, "bot", bot_id or 0, "humor_sync")
        if humor and humor[0].weight > 0.3:
            bonus += 15

        # recent shared joke → +15
        jokes = self._get_active_events("joke", chat_id, user_id, limit=1)
        if jokes:
            bonus += 15

        # unresolved conflict → +25
        conflicts = self._get_active_events("conflict", chat_id, user_id)
        if conflicts:
            bonus += 25

        # no social connection at all → -20
        all_edges = self._get_edges("user", user_id, None, None)
        if not all_edges:
            bonus -= 20

        return bonus

    # ─── internal helpers ──────────────────────────────────────────

    def _extract_topics(self, text: str) -> list[str]:
        topics: list[str] = []
        for match in TOPIC_MARKER_RE.finditer(text):
            word = match.group(1).strip().lower()
            if len(word) >= 4 and word not in self._stopwords():
                topics.append(word)
        return topics

    def _update_topic_edge(self, user_id: int, topic: str, delta: float, edge_type: str, now: str) -> None:
        pass  # reserved for topic interest tracking

    def _update_edge(
        self,
        source_type: str,
        source_id: int,
        target_type: str | None,
        target_id: int | None,
        edge_type: str,
        delta: float,
        now: str,
        context_tag: str = "",
    ) -> None:
        if target_type is None or target_id is None:
            return
        if source_type == target_type and source_id == target_id:
            return

        with self._connect() as conn:
            row = conn.execute(
                "SELECT weight, context_tag FROM graph_edges WHERE source_type=? AND source_id=? AND target_type=? AND target_id=? AND edge_type=?",
                (source_type, source_id, target_type, target_id, edge_type),
            ).fetchone()

            if row:
                new_weight = max(-1.0, min(1.0, row["weight"] + delta))
                tag = context_tag or row["context_tag"]
                conn.execute(
                    "UPDATE graph_edges SET weight=?, context_tag=?, last_interaction=? WHERE source_type=? AND source_id=? AND target_type=? AND target_id=? AND edge_type=?",
                    (new_weight, tag, now, source_type, source_id, target_type, target_id, edge_type),
                )
            else:
                conn.execute(
                    "INSERT INTO graph_edges (source_type, source_id, target_type, target_id, edge_type, weight, context_tag, last_interaction) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (source_type, source_id, target_type, target_id, edge_type, delta, context_tag, now),
                )

    def _get_edges(
        self,
        source_type: str,
        source_id: int,
        target_type: str | None = None,
        target_id: int | None = None,
        edge_type: str | None = None,
    ) -> list[SocialEdge]:
        parts = ["source_type=? AND source_id=?"]
        params: list = [source_type, source_id]
        if target_type is not None:
            parts.append("target_type=?")
            params.append(target_type)
        if target_id is not None:
            parts.append("target_id=?")
            params.append(target_id)
        if edge_type is not None:
            parts.append("edge_type=?")
            params.append(edge_type)

        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT source_type, source_id, target_type, target_id, edge_type, weight, context_tag, last_interaction FROM graph_edges WHERE {' AND '.join(parts)} ORDER BY last_interaction DESC LIMIT 10",
                params,
            ).fetchall()

        return [
            SocialEdge(
                source_type=r["source_type"],
                source_id=r["source_id"],
                target_type=r["target_type"],
                target_id=r["target_id"],
                edge_type=r["edge_type"],
                weight=r["weight"],
                context_tag=r["context_tag"],
                last_interaction=r["last_interaction"],
            )
            for r in rows
        ]

    def _recent_users(self, chat_id: int, exclude_user_id: int, limit: int = 8) -> list[int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT user_id FROM messages WHERE chat_id=? AND user_id!=? AND is_bot=0 ORDER BY id DESC LIMIT ?",
                (chat_id, exclude_user_id, limit),
            ).fetchall()
        return [r["user_id"] for r in rows]

    def _record_event(
        self,
        event_type: str,
        description: str,
        involved_users: list[int],
        chat_id: int,
        impact_score: float,
        now: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO graph_events (event_type, description, involved_users, chat_id, impact_score, created_at, resolved) VALUES (?, ?, ?, ?, ?, ?, 0)",
                (event_type, description, json.dumps(involved_users), chat_id, impact_score, now),
            )

    def _get_active_events(
        self,
        event_type: str,
        chat_id: int,
        user_id: int | None = None,
        limit: int = 3,
    ) -> list[SocialEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, event_type, description, involved_users, chat_id, impact_score, created_at, resolved FROM graph_events WHERE event_type=? AND chat_id=? AND resolved=0 ORDER BY created_at DESC LIMIT ?",
                (event_type, chat_id, limit),
            ).fetchall()

        result: list[SocialEvent] = []
        for r in rows:
            users = json.loads(r["involved_users"])
            if user_id is not None and user_id not in users:
                continue
            result.append(SocialEvent(
                event_id=r["id"],
                event_type=r["event_type"],
                description=r["description"],
                involved_users=users,
                chat_id=r["chat_id"],
                impact_score=r["impact_score"],
                created_at=r["created_at"],
                resolved=bool(r["resolved"]),
            ))
        return result

    def resolve_event(self, event_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE graph_events SET resolved=1 WHERE id=?", (event_id,))

    def all_edges(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT source_type, source_id, target_type, target_id, edge_type, weight, context_tag, last_interaction FROM graph_edges ORDER BY last_interaction DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def all_events(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, event_type, description, involved_users, chat_id, impact_score, created_at, resolved FROM graph_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["involved_users"] = json.loads(d["involved_users"])
            except (json.JSONDecodeError, TypeError):
                pass
            d["resolved"] = bool(d["resolved"])
            result.append(d)
        return result

    def edge_count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]

    def event_count(self, event_type: str | None = None) -> int:
        with self._connect() as conn:
            if event_type:
                return conn.execute(
                    "SELECT COUNT(*) FROM graph_events WHERE event_type=?", (event_type,)
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM graph_events").fetchone()[0]

    def _resolve_username(self, user_id: int) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT username FROM users WHERE user_id=?",
                (user_id,),
            ).fetchone()
        if row and row["username"]:
            return row["username"]
        return str(user_id)

    @staticmethod
    def _weight_symbol(weight: float) -> str:
        if weight >= 0.6:
            return "🔥"
        if weight >= 0.3:
            return "👍"
        if weight >= 0.0:
            return "➖"
        if weight >= -0.3:
            return "👎"
        return "💢"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _stopwords() -> set[str]:
        return {
            "котор", "чтобы", "также", "можно", "этого", "всего", "комна",
            "просто", "потом", "после", "перед", "через", "будто", "будто",
            "конеч", "самые", "своим", "будет", "иметь", "сегод",
        }
