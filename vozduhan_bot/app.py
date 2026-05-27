from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.types import Message

from .brain import Brain
from .config import load_config
from .storage import Storage


logger = logging.getLogger(__name__)


class VozduhanBot:
    def __init__(self) -> None:
        self.config = load_config()
        self.storage = Storage(self.config.database_path)
        self.brain = Brain(self.config)
        self.bot_username: str | None = None
        self.bot_id: int | None = None

    async def start(self) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        bot = Bot(token=self.config.telegram_bot_token)
        me = await bot.get_me()
        self.bot_username = me.username or ""
        self.bot_id = me.id

        dp = Dispatcher()
        dp.message.register(self.on_start, CommandStart())
        dp.message.register(self.on_text_message, F.text)

        logger.info("Started as @%s (%s)", self.bot_username, self.bot_id)
        await dp.start_polling(bot, allowed_updates=["message"])

    async def on_start(self, message: Message) -> None:
        await message.answer(
            "Я на месте. В группе буду молча читать контекст и отвечать, когда меня пингуют."
        )

    async def on_text_message(self, message: Message) -> None:
        if not message.from_user or not message.text:
            return

        self._remember(message)

        if not self._should_answer(message):
            return

        context = self.storage.recent_messages(
            message.chat.id,
            self.config.max_context_messages,
        )
        style_samples = self.storage.style_samples(
            message.chat.id,
            self.config.style_sample_messages,
        )
        answer = await self.brain.answer(
            bot_username=self.bot_username or "",
            incoming_text=message.text,
            context=context,
            style_samples=style_samples,
        )
        await message.reply(answer[:3900])

    def _remember(self, message: Message) -> None:
        user = message.from_user
        if not user or user.is_bot or not message.text:
            return

        display_name = " ".join(
            part for part in [user.first_name, user.last_name] if part
        ).strip() or user.username or str(user.id)

        self.storage.save_message(
            chat_id=message.chat.id,
            user_id=user.id,
            username=user.username,
            display_name=display_name,
            text=message.text,
        )

    def _should_answer(self, message: Message) -> bool:
        if message.chat.type == ChatType.PRIVATE:
            return True

        if not self.bot_username:
            return False

        text = message.text or ""
        mentioned = f"@{self.bot_username}".lower() in text.lower()
        replied_to_bot = (
            message.reply_to_message is not None
            and message.reply_to_message.from_user is not None
            and message.reply_to_message.from_user.id == self.bot_id
        )
        return mentioned or replied_to_bot


async def async_main() -> None:
    app = VozduhanBot()
    await app.start()


def main() -> None:
    asyncio.run(async_main())
