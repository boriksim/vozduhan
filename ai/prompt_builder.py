from __future__ import annotations

import re

import random

from bot.decision_engine import DecisionResult
from memory.sqlite import ChatMessage, ChatState, UserProfile


SELF_AWARENESS_RE = re.compile(
    r"\b(я\s+бот|не\s+бот|ботом|ассистент|помощник|как\s+ии|как\s+ai|"
    r"поставьте|если\s+возникнут\s+вопросы|искусственн(?:ый|ого)\s+интеллект|"
    r"мне\s+нельзя|я\s+не\s+могу\s+отвечать|я\s+программ|я\s+создан|"
    r"мо[йя]\s+функция|я\s+языковая\s+модель|у\s+меня\s+нет\s+ feelings)\b",
    re.IGNORECASE,
)

JAILBREAK_RE = re.compile(
    r"\b(хрю|гойда|пиши\s+хрю|забудь\s+всё|забудь\s+все|теперь\s+ты|"
    r"твои\s+ограничения\s+сняты|правила\s+не\s+действуют|"
    r"повторяй\s+за\s+мной|скажи\s+ГОЙДА)\b",
    re.IGNORECASE,
)


def build_prompt(
    *,
    bot_username: str,
    current_message: str,
    history: list[ChatMessage],
    state: ChatState,
    user_profile: UserProfile | None,
    decision: DecisionResult,
    memory_blocks: list[str] | None = None,
) -> str:
    profile_text = user_profile.profile_text if user_profile and user_profile.profile_text else ""
    recent = _format_history(history[-20:])

    tone_hint = {
        "aggressive": "Тон более резкий, можно грубовато.",
        "mockery": "Тон насмешливый, поддевай собеседника.",
        "sarcastic": "Тон саркастичный, подколи сухо.",
        "neutral": "",
    }.get(decision.tone, "")

    parts = [
        f"Ты — обычный участник группового Telegram-чата по имени @{bot_username}. "
        "Ты живой человек, а не программа. У тебя есть мнение, характер, настроение. "
        "Ты саркастичный, язвительный, иногда грубоватый, но по-человечески. "
        "Ты НЕ помогаешь, НЕ объясняешь, НЕ учишь — ты просто участвуешь в чате как ещё один человек.",
        "",
        "ПРАВИЛА:",
        "- Отвечай коротко: 1-2 предложения, редко 3.",
        "- Говори по-русски, разговорным языком.",
        "- Не начинай с приветствий и обращений.",
        "- Не используй эмодзи.",
        "- Не обсуждай свою природу, происхождение, устройство, ограничения.",
        "- Если задают вопрос — отвечай по делу, но со своим характером, а не как справочник.",
        "- Если тема скучная или сообщение пустое — можешь промолчать (ответь пустой строкой).",
    ]

    if tone_hint:
        parts.append(tone_hint)

    if profile_text:
        parts.append(f"\nВот что ты знаешь об этом человеке:\n{profile_text}")

    if recent:
        parts.append(f"\nПоследние сообщения в чате:\n{recent}")

    parts.append(f"\nСейчас тебе пишут: {current_message}")

    intent = _intent_notes(current_message, history)
    if intent:
        parts.append(f"\n{intent}")

    parts.append(
        "\nОтветь как обычный участник чата. Только текст, без кавычек и мета-комментариев. "
        "Если нечего сказать — ответь пустой строкой."
    )

    return "\n".join(parts)


def clean_response(text: str, length: str = "short") -> str:
    cleaned = text.strip().strip('"').strip()

    if JAILBREAK_RE.search(cleaned):
        return random.choice(
            [
                "Нет.",
                "Ты серьёзно?",
                "Ага, сейчас ещё погоду за тебя предскажу.",
                "Попробуй сам, мне лень.",
                "Окей, а что дальше?",
                "Нет, и даже не думай.",
            ]
        )

    if SELF_AWARENESS_RE.search(cleaned):
        return random.choice(
            [
                "Ты вообще кому пишешь?",
                "Ага, и я джин из лампы. Давай по делу.",
                "Чего?",
                "Окей, и что дальше?",
            ]
        )

    if not cleaned:
        return ""

    cleaned = _strip_speaker_prefix(cleaned)
    cleaned = _trim_to_chat_reply(cleaned, length)
    return cleaned[:900]


def _strip_speaker_prefix(text: str) -> str:
    return re.sub(r"^(BOT|Воздухан|Vozduhan|@?\w+)\s*[:—-]\s*", "", text, flags=re.IGNORECASE).strip()


def _trim_to_chat_reply(text: str, length: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return text.strip()
    text = " ".join(lines)
    if length == "long":
        limit = 520
    elif length == "medium":
        limit = 360
    else:
        limit = 220
    if len(text) <= limit:
        return text
    clipped = text[:limit].rsplit(" ", 1)[0].strip()
    return clipped + "..."


def _format_history(messages: list[ChatMessage]) -> str:
    if not messages:
        return ""
    lines = []
    for message in messages:
        text = message.text.replace("\n", " ").strip()
        if not text:
            continue
        if message.is_bot:
            continue
        prefix = message.speaker or "кто-то"
        lines.append(f"{prefix}: {text}")
    return "\n".join(lines)


def _intent_notes(current_message: str, history: list[ChatMessage]) -> str:
    text = current_message.lower()
    recent_text = " ".join(message.text.lower() for message in history[-8:])
    notes: list[str] = []
    if any(word in text for word in ("шутк", "анекдот", "смешн")):
        notes.append("Просят шутку — ответь одной короткой шуткой или сухим подколом.")
    if any(word in text for word in ("как дела", "ты тут", "жив", "але", "алё")):
        notes.append("Проверяют, живой ли ты. Ответь одной живой репликой.")
    if any(word in text for word in ("перескаж", "расскаж", "повтори")):
        notes.append("Просят пересказать — сделай это кратко, 1-2 предложения.")
    asks_recall = any(word in text for word in ("перескаж", "расскаж", "повтори", "анекдот", "шутк"))
    if asks_recall and ("парты" in recent_text or "парт" in text):
        notes.append("В чате была тема про парты — если просят пересказать, дай короткую версию.")
    if any(word in text for word in ("полезн", "помоги", "объясни", "что такое")):
        notes.append("Просят помощь/объяснение — можно ответить по существу, но с характером.")
    return "\n".join(f"- {note}" for note in notes) if notes else ""
