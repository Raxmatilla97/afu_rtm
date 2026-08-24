"""The worker's half of the bot's anchor-message convention.

The bot keeps exactly one "screen" message per chat and edits it in place; the id lives in
Redis under ``bot:anchor:{chat_id}``. The worker sends messages into the same chats, so it
has to respect that convention — otherwise a stale screen sits above whatever the worker
just delivered, still offering buttons that no longer make sense.

The key is duplicated rather than imported because the worker cannot import the bot
package. It is one string, and both sides name it in a comment.
"""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from redis.asyncio import Redis

from afu_shared.settings import settings

logger = logging.getLogger(__name__)

#: Mirrors ``bot/app/ui/anchor.py``.
ANCHOR_KEY_TMPL = "bot:anchor:{chat_id}"
ANCHOR_TTL_SECONDS = 30 * 24 * 3600


def _redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def drop_anchor(bot: Bot, chat_id: int) -> None:
    """Delete the chat's current screen and forget it."""
    redis = _redis()
    try:
        key = ANCHOR_KEY_TMPL.format(chat_id=chat_id)
        stored = await redis.get(key)
        if stored:
            try:
                await bot.delete_message(chat_id, int(stored))
            except (TelegramBadRequest, TelegramForbiddenError):
                logger.debug("Anchor %s in chat %s already gone", stored, chat_id)
            await redis.delete(key)
    finally:
        await redis.aclose()


async def claim_anchor(chat_id: int, message_id: int) -> None:
    """Register a message the worker just sent as the chat's screen.

    Used for messages that are genuinely the next step the user has to act on, so that the
    bot's own ``render(force_new=True)`` cleans them up when that step is done. The
    post-OAuth "share your phone number" prompt is the motivating case: it is obsolete the
    moment the contact arrives, and without this it stayed in the chat forever.
    """
    redis = _redis()
    try:
        await redis.set(
            ANCHOR_KEY_TMPL.format(chat_id=chat_id), message_id, ex=ANCHOR_TTL_SECONDS
        )
    finally:
        await redis.aclose()
