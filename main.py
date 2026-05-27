from __future__ import annotations

import asyncio
import logging

import uvicorn

from bot.telegram import TelegramBotRunner
from config import load_config
from memory.sqlite import SQLiteMemory
from web.app import create_app


async def run_web(config, memory: SQLiteMemory) -> None:
    app = create_app(memory)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=config.web_host,
            port=config.web_port,
            log_level="info",
        )
    )
    await server.serve()


async def async_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config()
    memory = SQLiteMemory(config.database_path)
    runner = TelegramBotRunner(config, memory)

    try:
        await asyncio.gather(
            runner.start(),
            run_web(config, memory),
        )
    finally:
        await runner.close()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
