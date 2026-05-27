from __future__ import annotations

import aiohttp
import logging

logger = logging.getLogger(__name__)


class OllamaUnavailable(Exception):
    """Raised when Ollama server is not reachable (PC is off)."""


class OllamaClient:
    def __init__(self, url: str, model: str) -> None:
        self.url = url
        self.model = model
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=60, sock_connect=5)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.5,
                "top_p": 0.8,
                "repeat_penalty": 1.15,
                "num_predict": 120,
            },
        }
        session = await self._get_session()
        try:
            async with session.post(self.url, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
            return (data.get("response") or "").strip()
        except (aiohttp.ClientConnectorError, aiohttp.ClientTimeout) as exc:
            logger.warning("Ollama is not reachable: %s", exc)
            raise OllamaUnavailable() from exc

    async def summarize_profile(self, username: str, messages: list[str], old_profile: str = "") -> str:
        prompt = "\n".join(
            [
                "Сделай короткий профиль участника Telegram-чата.",
                "Опиши стиль общения, поведение, отношение к спору. Без морализаторства.",
                "Максимум 5 коротких пунктов.",
                "",
                f"Участник: {username}",
                f"Старый профиль: {old_profile or '(нет)'}",
                "Сообщения:",
                "\n".join(f"- {message}" for message in messages[-40:]),
            ]
        )
        return await self.generate(prompt)
