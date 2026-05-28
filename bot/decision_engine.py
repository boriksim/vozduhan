from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import random
import re

from memory.sqlite import ChatMessage, ChatState, UserProfile


CONFLICT_RE = re.compile(
    r"\b(спор|срач|конфликт|руга|оскорб|токсич|ненавиж|достал|задолбал|бред)\b",
    re.IGNORECASE,
)
TOXIC_RE = re.compile(
    r"\b(идиот|дурак|тупой|заткнись|пошел|пошёл|хер|говно|клоун|ничтож)\b",
    re.IGNORECASE,
)
BORING_RE = re.compile(r"^(ок|ага|ясно|понятно|лол|ахах|хаха|\+|спс|да|нет)\.?$", re.IGNORECASE)
ADDRESS_RE = re.compile(
    r"\b(воздухан|что\s+скажешь|как\s+дела\s+у\s+тебя|ты\s+тут)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DecisionContext:
    current_message: str
    recent_messages: list[ChatMessage]
    state: ChatState
    user_profile: UserProfile | None
    bot_username: str
    bot_id: int | None
    last_response_at: str | None
    intervention_mode: bool
    user_id: int | None = None
    is_private: bool = False
    is_reply_to_bot: bool = False
    graph_bonus: int = 0


@dataclass(frozen=True)
class DecisionResult:
    respond: bool
    reason: str
    priority: int
    tone: str
    length: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def decide_to_respond(context: DecisionContext) -> DecisionResult:
    text = context.current_message.strip()
    lowered = text.lower()
    score = 0
    reasons: list[str] = []

    mentioned = bool(context.bot_username and f"@{context.bot_username.lower()}" in lowered)
    addressed = context.is_reply_to_bot or bool(ADDRESS_RE.search(lowered))
    conflict = bool(CONFLICT_RE.search(text))
    toxic = bool(TOXIC_RE.search(text))
    boring = bool(BORING_RE.match(text)) or len(text) < 2
    recent_bot_messages = [message for message in context.recent_messages[-10:] if message.is_bot]
    messages_since_bot = _messages_since_last_bot(context.recent_messages)
    cooldown_seconds = _seconds_since(context.last_response_at)
    conversation_dead = _conversation_dead(context.recent_messages)

    if context.is_private:
        score += 80
        reasons.append("private chat")
    if mentioned:
        score += 100
        reasons.append("mentioned")
    if addressed:
        score += 50
        reasons.append("addressed")
    if conflict:
        score += 20
        reasons.append("conflict")
    if toxic:
        score += 15
        reasons.append("toxicity")
    if context.state.engagement > 0.7:
        score += 10
        reasons.append("high engagement")
    if context.intervention_mode:
        score += 10
        reasons.append("intervention mode")
    if 2 <= len(text) <= 24 and not boring:
        score += 5
        reasons.append("short joke window")

    if context.state.irritation > 0.7:
        score += 10
        reasons.append("irritated")
    if context.state.engagement < 0.3 and not mentioned and not addressed:
        score -= 15
        reasons.append("low engagement")

    if (
        cooldown_seconds is not None
        and cooldown_seconds < random.randint(20, 90)
        and not context.is_private
    ):
        score -= 40
        reasons.append("cooldown")
    if recent_bot_messages and not context.is_private:
        score -= 30
        reasons.append("already spoke recently")
    if boring:
        score -= 20
        reasons.append("boring")
    if conversation_dead:
        score -= 15
        reasons.append("conversation dead")
    if (
        messages_since_bot is not None
        and messages_since_bot < 5
        and not mentioned
        and not addressed
        and not context.is_private
    ):
        score -= 100
        reasons.append("anti-spam: less than 5 messages since last response")

    if not mentioned and not addressed and not conflict and not toxic and not boring:
        random_chance = random.uniform(0.12, 0.25)
        if context.state.engagement > 0.6:
            random_chance += 0.10
        if context.state.irritation > 0.6:
            random_chance += 0.08
        if context.intervention_mode and random.random() < random_chance:
            score += 35
            reasons.append("random intervention")

    if context.graph_bonus:
        score += context.graph_bonus
        reasons.append(f"graph: {context.graph_bonus}")

    priority = max(0, min(100, score))
    respond = mentioned or addressed or score >= 45

    is_intervention = "random intervention" in reasons

    if (
        messages_since_bot is not None
        and messages_since_bot < 5
        and not mentioned
        and not addressed
        and not is_intervention
        and not context.is_private
    ):
        respond = False

    return DecisionResult(
        respond=respond,
        reason=", ".join(reasons) or "no strong signal",
        priority=priority,
        tone=_tone(context.state, conflict, toxic, mentioned),
        length=_length(text, context.state, addressed or mentioned, conflict, context.user_id, context.recent_messages),
    )


def _tone(state: ChatState, conflict: bool, toxic: bool, mentioned: bool) -> str:
    if toxic or state.irritation > 0.7:
        return "aggressive"
    if conflict:
        return "mockery"
    if mentioned:
        return "sarcastic"
    return "neutral"


def _length(text: str, state: ChatState, directly_asked: bool, conflict: bool, user_id: int | None = None, recent_messages: list[ChatMessage] | None = None) -> str:
    if state.mood < -0.5:
        return "short"
    if directly_asked and "?" in text:
        return "medium"
    if conflict and state.engagement > 0.7:
        return "medium"
    # For users who repeat themselves, give longer, more engaged responses
    if user_id is not None and recent_messages is not None:
        recent_user_messages = [m for m in recent_messages[-10:] if m.user_id == user_id and not m.is_bot]
        if len(recent_user_messages) >= 3:
            # Check if user is repeating similar messages
            recent_texts = [m.text.lower().strip() for m in recent_user_messages]
            if len(set(recent_texts)) < len(recent_texts) * 0.7:  # High repetition
                return "long"  # Give longer, more engaged response to break the cycle
    return "short"


def _seconds_since(value: str | None) -> float | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - moment).total_seconds()


def _messages_since_last_bot(messages: list[ChatMessage]) -> int | None:
    for index, message in enumerate(reversed(messages)):
        if message.is_bot:
            return index
    return None


def _conversation_dead(messages: list[ChatMessage]) -> bool:
    if len(messages) < 2:
        return True
    try:
        last = datetime.fromisoformat(messages[-1].timestamp)
        prev = datetime.fromisoformat(messages[-2].timestamp)
    except ValueError:
        return False
    return (last - prev).total_seconds() > 900
