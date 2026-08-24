"""Remembering which request a bot message was about.

Telegram's own reply is what people actually reach for: a notification arrives, they hold
it, and they type an answer. Before this that answer went nowhere — the bot saw an ordinary
message with no conversation state and fell through to "I didn't understand", so the most
natural way to reply was the one way that did not work.

The link is kept in Redis rather than in a column because it is disposable: it only has to
outlive the window in which somebody might still reply to a given message, and losing it
costs one "please use the button" instead of corrupting anything.
"""

import logging

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

KEY_TMPL = "bot:msgreq:{chat_id}:{message_id}"
#: Long enough that replying to last week's notification still works, short enough that the
#: keyspace stays proportional to recent activity.
TTL_SECONDS = 30 * 24 * 3600


def _key(chat_id: int, message_id: int) -> str:
    return KEY_TMPL.format(chat_id=chat_id, message_id=message_id)


async def remember(redis: Redis, chat_id: int, message_id: int, request_id: int) -> None:
    await redis.set(_key(chat_id, message_id), request_id, ex=TTL_SECONDS)


async def remember_many(
    redis: Redis, chat_id: int, message_ids: list[int], request_id: int
) -> None:
    """Link a whole batch — a notification plus the files sent under it.

    Replying to any one of them means the same thing, and a user who answers by holding the
    photo rather than the text should not be treated differently.
    """
    for message_id in message_ids:
        await remember(redis, chat_id, message_id, request_id)


async def lookup(redis: Redis, chat_id: int, message_id: int) -> int | None:
    raw = await redis.get(_key(chat_id, message_id))
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("Unusable request link for %s/%s: %r", chat_id, message_id, raw)
        return None
