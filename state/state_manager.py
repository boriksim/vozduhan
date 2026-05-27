from __future__ import annotations

import re

from memory.sqlite import ChatState, SQLiteMemory


CONFLICT_RE = re.compile(
    r"\b(спор|срач|туп|идиот|дурак|бред|ненавиж|заткнись|пошел|пошёл|хер|фигня|оскорб)\b",
    re.IGNORECASE,
)


class StateManager:
    def __init__(self, memory: SQLiteMemory) -> None:
        self.memory = memory

    def get(self, chat_id: int) -> ChatState:
        return self.memory.get_state(chat_id)

    def update_after_message(self, chat_id: int, text: str, addressed: bool) -> ChatState:
        state = self.memory.get_state(chat_id)
        toxic = bool(CONFLICT_RE.search(text))
        mood = state.mood
        irritation = state.irritation
        engagement = state.engagement

        if toxic:
            irritation += 0.08
            mood -= 0.04
            engagement += 0.02
        elif addressed:
            engagement += 0.025
            mood += 0.01
        else:
            irritation = max(0, irritation - 0.01)
            engagement = max(0, engagement - 0.01)
            mood -= 0.005

        self.memory.update_state(chat_id, mood, irritation, min(engagement, 0.85))
        return self.memory.get_state(chat_id)

    def update_after_response(self, chat_id: int) -> ChatState:
        state = self.memory.get_state(chat_id)
        self.memory.update_state(
            chat_id,
            mood=state.mood + 0.02,
            irritation=max(0, state.irritation - 0.03),
            engagement=min(state.engagement + 0.035, 0.85),
        )
        return self.memory.get_state(chat_id)
