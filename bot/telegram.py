from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher

from bot.handlers import BotHandlers
from config import Config
from memory.sqlite import SQLiteMemory


logger = logging.getLogger(__name__)


class TelegramBotRunner:
    def __init__(self, config: Config, memory: SQLiteMemory) -> None:
        self.config = config
        self.memory = memory
        self.handlers = BotHandlers(config, memory)

    async def start(self) -> None:
        bot = Bot(token=self.config.telegram_bot_token)
        me = await bot.get_me()
        username = me.username or self.config.bot_name_fallback
        self.handlers.bind_identity(username=username, bot_id=me.id)

        dispatcher = Dispatcher()
        dispatcher.include_router(self.handlers.router)

        logger.info("Telegram bot started as @%s (%s)", username, me.id)
        await dispatcher.start_polling(bot, allowed_updates=["message"])

    async def close(self) -> None:
        await self.handlers.ollama.close()
