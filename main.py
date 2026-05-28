from __future__ import annotations

import asyncio
import logging

import httpx
import uvicorn

from bot.telegram import TelegramBotRunner
from config import load_config
from memory.sqlite import SQLiteMemory
from web.app import create_app


logger = logging.getLogger(__name__)


async def self_ping(url: str, interval: int = 300) -> None:
    if not url:
        return
    client = httpx.AsyncClient()
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                await client.get(url, timeout=10)
            except Exception as exc:
                logger.warning("self-ping failed: %s", exc)
    finally:
        await client.aclose()


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

    tasks = [runner.start(), run_web(config, memory)]
    if config.self_ping_url:
        tasks.append(self_ping(config.self_ping_url))

    try:
        await asyncio.gather(*tasks)
    finally:
        await runner.close()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
