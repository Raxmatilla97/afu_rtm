from typing import Any

from aiogram import Bot
from aiogram.types import Message
from arq import ArqRedis
from redis.asyncio import Redis

TRANSIENT_KEY_TMPL = "bot:last_transient:{chat_id}"
TRANSIENT_DELETE_DEFER_SECONDS = 5


def _key(chat_id: int) -> str:
    return TRANSIENT_KEY_TMPL.format(chat_id=chat_id)


async def schedule_delete(
    arq_pool: ArqRedis, chat_id: int, message_id: int, *, defer_seconds: int = TRANSIENT_DELETE_DEFER_SECONDS
) -> None:
    """Delete a message ~defer_seconds from now. Works for the bot's own messages and, in a
    private chat, for the user's messages too (Telegram allows a bot to delete either side's
    messages in a private 1:1 chat within 48h)."""
    await arq_pool.enqueue_job("delete_telegram_message", chat_id, message_id, _defer_by=defer_seconds)


async def send_transient(
    bot: Bot, redis: Redis, arq_pool: ArqRedis, chat_id: int, text: str, **kwargs: Any
) -> Message:
    """Send a bot message and schedule deletion of whatever bot message was transient before it.
    Use for menu prompts / one-off toasts. Never use for durable messages (ticket confirmations,
    completion notices) — those are sent with bot.send_message directly and never touched here."""
    previous_id = await redis.get(_key(chat_id))
    message = await bot.send_message(chat_id, text, **kwargs)
    if previous_id:
        await schedule_delete(arq_pool, chat_id, int(previous_id))
    await redis.set(_key(chat_id), message.message_id, ex=3600)
    return message
