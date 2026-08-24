"""Recognising a Telegram reply to something the bot said about a request."""

from aiogram.filters import Filter
from aiogram.types import Message
from redis.asyncio import Redis

from afu_shared.message_links import lookup


class RepliedRequest(Filter):
    """Passes when the message is a reply to a bot notification, naming its request.

    Implemented as a filter rather than as a check inside the handler so that a reply to
    something *else* — a colleague's message, an old bot message we no longer have a link
    for — falls through to the handlers below instead of being swallowed here.

    Returns the request id as handler data, so the handler never repeats the lookup.
    """

    async def __call__(self, message: Message, redis: Redis) -> dict | bool:
        if message.reply_to_message is None:
            return False
        request_id = await lookup(
            redis, message.chat.id, message.reply_to_message.message_id
        )
        if request_id is None:
            return False
        return {"linked_request_id": request_id}
