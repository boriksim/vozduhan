from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    database_path: str
    groq_api_key: str
    groq_model: str
    max_context_messages: int
    profile_update_every: int
    generation_timeout_seconds: float
    web_host: str
    web_port: int
    bot_name_fallback: str
    self_ping_url: str


def load_config() -> Config:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required. Put it into .env.")

    return Config(
        telegram_bot_token=token,
        database_path=os.getenv("DATABASE_PATH", "data/vozduhan.sqlite3").strip(),
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip(),
        max_context_messages=int(os.getenv("MAX_CONTEXT_MESSAGES", "30")),
        profile_update_every=int(os.getenv("PROFILE_UPDATE_EVERY", "25")),
        generation_timeout_seconds=float(os.getenv("GENERATION_TIMEOUT_SECONDS", "25")),
        web_host=os.getenv("WEB_HOST", "0.0.0.0").strip(),
        web_port=int(os.getenv("PORT") or os.getenv("WEB_PORT", "8080")),
        bot_name_fallback=os.getenv("BOT_NAME_FALLBACK", "vozduhan").strip(),
        self_ping_url=os.getenv("SELF_PING_URL", "").strip(),
    )
