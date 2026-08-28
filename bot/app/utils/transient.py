"""Short-lived bot messages that clean themselves up.

Never use these for durable output — ticket confirmations, completion notices and messages
from the other party must stay in the chat.
"""

from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import Message
from arq import ArqRedis
from redis.asyncio import Redis

TRANSIENTS_KEY_TMPL = "bot:transients:{chat_id}"
TRANSIENT_DELETE_DEFER_SECONDS = 5
#: Cap the tracked list; a runaway chat should not grow an unbounded Redis key.
MAX_TRACKED = 10

#: Replayed attachments. Tracked separately from transients because they must NOT expire on
#: a timer — the user asked to see them and may be watching a two-minute video — but must
#: not outlive the screen that produced them either. They are cleared the moment the user
#: navigates anywhere else, which is what keeps the chat clean.
MEDIA_KEY_TMPL = "bot:media:{chat_id}"
MAX_TRACKED_MEDIA = 40


#: Messages that must NOT expire on a timer or on the next screen change: the "we emailed
#: you a reset link" notice. It has to survive the user leaving Telegram, opening their
#: mail, resetting the password on the web and coming back — which is exactly the journey
#: a transient would not survive. Cleared explicitly once they log in again.
STICKY_KEY_TMPL = "bot:sticky:{chat_id}"
MAX_TRACKED_STICKY = 5


def _key(chat_id: int) -> str:
    return TRANSIENTS_KEY_TMPL.format(chat_id=chat_id)


def _media_key(chat_id: int) -> str:
    return MEDIA_KEY_TMPL.format(chat_id=chat_id)


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


async def track_media(redis: Redis, chat_id: int, message_ids: list[int]) -> None:
    """Remember replayed attachments so the next screen change can clear them."""
    if not message_ids:
        return
    key = _media_key(chat_id)
    await redis.lpush(key, *message_ids)
    await redis.ltrim(key, 0, MAX_TRACKED_MEDIA - 1)
    await redis.expire(key, 24 * 3600)


async def purge_media(bot: Bot, redis: Redis, chat_id: int) -> None:
    """Delete the replayed attachments now.

    Immediate rather than queued: this runs as the user navigates, and the whole point is
    that the files are gone by the time the new screen appears.
    """
    key = _media_key(chat_id)
    ids = await redis.lrange(key, 0, -1)
    if not ids:
        return
    await redis.delete(key)
    for raw in ids:
        try:
            await bot.delete_message(chat_id, int(raw))
        except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
            # Already gone, older than 48h, or blocked — none of it worth reporting.
            pass


def _sticky_key(chat_id: int) -> str:
    return STICKY_KEY_TMPL.format(chat_id=chat_id)


async def remember_sticky(redis: Redis, chat_id: int, message_id: int) -> None:
    """Keep this message until something explicitly clears it."""
    key = _sticky_key(chat_id)
    await redis.lpush(key, message_id)
    await redis.ltrim(key, 0, MAX_TRACKED_STICKY - 1)
    # A week: long enough for somebody to reset a password over a weekend, short enough
    # that an abandoned chat does not keep the key forever.
    await redis.expire(key, 7 * 24 * 3600)


async def clear_sticky(bot: Bot, redis: Redis, chat_id: int) -> None:
    """Delete the kept messages now — the thing they were about has happened."""
    key = _sticky_key(chat_id)
    ids = await redis.lrange(key, 0, -1)
    if not ids:
        return
    await redis.delete(key)
    for raw in ids:
        try:
            await bot.delete_message(chat_id, int(raw))
        except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
            pass
