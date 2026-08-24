"""Auto-deletes the user's own messages after they have been handled.

Commands, menu taps and typed answers are all consumed into the anchor screen, so leaving
them in the chat is pure clutter. Centralising this replaces the scattered per-handler
``schedule_delete`` calls that previously covered only some entry points.

**Private chats only.** In a group this same behaviour would be the bot deleting people's
messages out of a shared conversation — the anchor-screen reasoning does not apply there,
and the group has its own message the bot maintains instead.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import Message, TelegramObject
from arq import ArqRedis

from app.utils.transient import schedule_delete


class AutoCleanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        result = await handler(event, data)

        if isinstance(event, Message) and event.chat.type == ChatType.PRIVATE:
            arq_pool: ArqRedis | None = data.get("arq_pool")
            if arq_pool is not None:
                await schedule_delete(arq_pool, event.chat.id, event.message_id)

        return result
