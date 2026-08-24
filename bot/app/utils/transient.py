"""Short-lived bot messages that clean themselves up.

Never use these for durable output — ticket confirmations, completion notices and messages
from the other party must stay in the chat.
"""

from typing import Any

from aiogram import Bot
from aiogram.types import Message
from arq import ArqRedis
from redis.asyncio import Redis

TRANSIENTS_KEY_TMPL = "bot:transients:{chat_id}"
TRANSIENT_DELETE_DEFER_SECONDS = 5
#: Cap the tracked list; a runaway chat should not grow an unbounded Redis key.
MAX_TRACKED = 10


def _key(chat_id: int) -> str:
    return TRANSIENTS_KEY_TMPL.format(chat_id=chat_id)


async def schedule_delete(
    arq_pool: ArqRedis,
    chat_id: int,
    message_id: int,
    *,
    defer_seconds: int = TRANSIENT_DELETE_DEFER_SECONDS,
) -> None:
    """Ask the worker to delete a message after a delay.

    The worker job swallows "already gone" errors, so deleting twice is harmless and no
    cancellation bookkeeping is needed.
    """
    await arq_pool.enqueue_job(
        "delete_telegram_message", chat_id, message_id, _defer_by=defer_seconds
    )


async def send_transient(
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
    chat_id: int,
    text: str,
    *,
    ttl: int = TRANSIENT_DELETE_DEFER_SECONDS,
    **kwargs: Any,
) -> Message:
    """Send a message that deletes itself shortly afterwards."""
    message = await bot.send_message(chat_id, text, **kwargs)

    key = _key(chat_id)
    await redis.lpush(key, message.message_id)
    await redis.ltrim(key, 0, MAX_TRACKED - 1)
    await redis.expire(key, 3600)

    await schedule_delete(arq_pool, chat_id, message.message_id, defer_seconds=ttl)
    return message


async def purge_transients(redis: Redis, arq_pool: ArqRedis, chat_id: int) -> None:
    """Drop every tracked transient now, e.g. on /cancel or when changing screens."""
    key = _key(chat_id)
    ids = await redis.lrange(key, 0, -1)
    for raw in ids:
        await schedule_delete(arq_pool, chat_id, int(raw), defer_seconds=0)
    await redis.delete(key)
