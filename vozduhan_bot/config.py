from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    openai_api_key: str | None
    openai_model: str
    database_path: str
    max_context_messages: int
    style_sample_messages: int


def load_config() -> Config:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required. Put it into .env.")

    return Config(
        telegram_bot_token=token,
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
        database_path=os.getenv("DATABASE_PATH", "data/vozduhan.sqlite3").strip(),
        max_context_messages=int(os.getenv("MAX_CONTEXT_MESSAGES", "80")),
        style_sample_messages=int(os.getenv("STYLE_SAMPLE_MESSAGES", "160")),
    )
