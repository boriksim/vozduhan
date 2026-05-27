from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class GroqUnavailable(Exception):
    pass


class GroqClient:
    def __init__(self, api_key: str, model: str = "llama3-70b-8192") -> None:
        self.api_key = api_key
        self.model = model
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def generate(self, prompt: str) -> str:
        client = await self._get_client()
        try:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,
                    "max_tokens": 200,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return (data["choices"][0]["message"]["content"] or "").strip()
        except httpx.HTTPStatusError as exc:
            logger.warning("Groq returned an error: %s", exc)
            raise GroqUnavailable() from exc
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning("Groq is not reachable: %s", exc)
            raise GroqUnavailable() from exc

    async def summarize_profile(
        self, username: str, messages: list[str], old_profile: str = ""
    ) -> str:
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
