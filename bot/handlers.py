from __future__ import annotations

import logging
import asyncio

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.types import Message

from ai.groq_client import GroqClient, GroqUnavailable
from ai.prompt_builder import build_prompt, clean_response
from bot.decision_engine import DecisionContext, decide_to_respond
from config import Config
from memory.sqlite import SQLiteMemory
from state.state_manager import StateManager


logger = logging.getLogger(__name__)


class BotHandlers:
    def __init__(self, config: Config, memory: SQLiteMemory) -> None:
        self.config = config
        self.memory = memory
        self.state = StateManager(memory)
        self.llm = GroqClient(config.groq_api_key, config.groq_model)
        self.router = Router()
        self.bot_username = config.bot_name_fallback
        self.bot_id: int | None = None
        self._register()

    def bind_identity(self, username: str, bot_id: int) -> None:
        self.bot_username = username
        self.bot_id = bot_id

    def _register(self) -> None:
        self.router.message.register(self.on_start, CommandStart())
        self.router.message.register(self.on_text_message, F.text)

    async def on_start(self, message: Message) -> None:
        await message.answer("О, меня позвали. Ну держитесь.")

    async def on_text_message(self, message: Message, bot: Bot) -> None:
        if not message.from_user or not message.text:
            return

        user = message.from_user
        if user.is_bot and user.id != self.bot_id:
            return

        display_name = " ".join(
            part for part in [user.first_name, user.last_name] if part
        ).strip() or user.username or str(user.id)

        self.memory.save_message(
            chat_id=message.chat.id,
            user_id=user.id,
            username=user.username,
            display_name=display_name,
            text=message.text,
            is_bot=user.id == self.bot_id,
        )

        if user.id == self.bot_id:
            return

        control = self.memory.get_control()
        if not control["enabled"]:
            return

        is_reply_to_bot = (
            message.reply_to_message is not None
            and message.reply_to_message.from_user is not None
            and message.reply_to_message.from_user.id == self.bot_id
        )
        mentioned = f"@{self.bot_username}".lower() in message.text.lower()
        addressed = mentioned or is_reply_to_bot or self._looks_addressed_to_bot(message.text)
        current_state = self.state.update_after_message(message.chat.id, message.text, addressed)
        history = self.memory.recent_messages(message.chat.id, self.config.max_context_messages)
        profile = self.memory.get_user_profile(user.id)

        decision = decide_to_respond(
            DecisionContext(
                current_message=message.text,
                recent_messages=history,
                state=current_state,
                user_profile=profile,
                bot_username=self.bot_username,
                bot_id=self.bot_id,
                last_response_at=control["last_response_at"],
                intervention_mode=bool(control["intervention_mode"]),
                is_private=message.chat.type == ChatType.PRIVATE,
                is_reply_to_bot=is_reply_to_bot,
            )
        )
        logger.info("decision chat=%s respond=%s priority=%s reason=%s", message.chat.id, decision.respond, decision.priority, decision.reason)

        await self._maybe_update_profile(user.id, user.username, profile, history)

        if not decision.respond:
            return

        prompt = build_prompt(
            bot_username=self.bot_username,
            current_message=message.text,
            history=history,
            state=current_state,
            user_profile=profile,
            decision=decision,
            memory_blocks=self._memory_blocks(profile),
        )

        try:
            answer = clean_response(
                await asyncio.wait_for(
                    self.llm.generate(prompt),
                    timeout=self.config.generation_timeout_seconds,
                ),
                decision.length,
            )
        except GroqUnavailable:
            logger.info("Groq unavailable")
            answer = "Мозг выключен, попробуй позже. Или пни разраба."
        except asyncio.TimeoutError:
            logger.warning("Groq generation timed out")
            answer = "Мозг уснул, попробуй позже. Или пни разраба."
        except Exception:
            logger.exception("Groq generation failed")
            answer = "О, локальный мозг опять ушёл смотреть в стену. Великолепный момент."

        if not answer:
            return

        answer = answer.replace(f"@{self.bot_username}", "").strip()
        if not answer:
            return

        sent = await message.reply(answer)
        self.memory.save_message(
            chat_id=sent.chat.id,
            user_id=self.bot_id or 0,
            username=self.bot_username,
            display_name=self.bot_username,
            text=answer,
            is_bot=True,
        )
        self.memory.mark_bot_response(message.chat.id)
        self.state.update_after_response(message.chat.id)

    async def _maybe_update_profile(
        self,
        user_id: int,
        username: str | None,
        profile,
        history,
    ) -> None:
        current_profile = profile or self.memory.get_user_profile(user_id)
        if not current_profile:
            return
        if current_profile.message_count == 0 or current_profile.message_count % self.config.profile_update_every != 0:
            return

        user_messages = [
            message.text
            for message in history
            if message.user_id == user_id and not message.is_bot
        ]
        if len(user_messages) < 5:
            return
        try:
            summary = await self.llm.summarize_profile(
                username=username or str(user_id),
                messages=user_messages,
                old_profile=current_profile.profile_text,
            )
        except Exception:
            logger.exception("Profile update failed")
            return
        if summary:
            self.memory.update_user_profile(user_id, username, summary[:1200])

    @staticmethod
    def _memory_blocks(profile) -> list[str]:
        if not profile or not profile.profile_text:
            return []
        return [line.strip("- ").strip() for line in profile.profile_text.splitlines() if line.strip()][:5]

    @staticmethod
    def _looks_addressed_to_bot(text: str) -> bool:
        lowered = text.lower().strip()
        return any(
            marker in lowered
            for marker in (
                "воздухан",
                "что скажешь",
                "как дела у тебя",
                "ты тут",
            )
        )
