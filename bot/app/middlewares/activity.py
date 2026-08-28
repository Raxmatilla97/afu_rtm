"""Recording that somebody used the bot, once per update.

The admin panel needs two things this bot never wrote down: how many people use it on a
given day, and what each person did last. Instrumenting forty handlers would have meant
forgetting several, so the accounting happens here — one row per update, written after the
handler has run.

A handler that knows something better than "pressed a button" calls :func:`mark`, and that
is written instead. The marker travels in a ``ContextVar`` rather than through the handler
signature because the interesting moments are usually two calls deep, in a helper that
never sees aiogram's data dict — threading a parameter down to each of them would be a
worse change than this one. aiogram runs every update in its own task, so the variable
belongs to exactly one update.

Nothing is recorded for somebody the bot cannot name: an anonymous update belongs to no
employee, and a feed row saying "— pressed a button" is not worth its storage.
"""

import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.activity import SOURCE_BOT, record
from afu_shared.models import Employee

logger = logging.getLogger(__name__)

_current: ContextVar[dict[str, Any] | None] = ContextVar("bot_activity", default=None)


def mark(
    action: str, *, target: str | None = None, employee: Employee | None = None
) -> None:
    """Name what this update actually did, replacing the generic entry.

    ``employee`` is for the login handlers: at the moment they run, the middleware's own
    idea of who is talking is still "nobody".
    """
    slot = _current.get()
    if slot is None:
        # Called outside an update (a worker job, a test) — nothing to attach it to.
        return
    slot["action"] = action
    slot["target"] = target
    if employee is not None:
        slot["employee"] = employee


def _generic(event: TelegramObject) -> tuple[str, str | None]:
    if isinstance(event, CallbackQuery):
        # The callback prefix tells one part of the bot from another without decoding
        # somebody else's payload format here.
        prefix = (event.data or "").split(":", 1)[0]
        return "bot.button", prefix or None
    if isinstance(event, Message):
        text = (event.text or "").strip()
        if text.startswith("/start"):
            return "bot.open", None
        if text.startswith("/"):
            return "bot.menu", text.split()[0][:40]
        return "bot.message", None
    return "bot.button", None


def _chat_of(event: TelegramObject):
    if isinstance(event, CallbackQuery):
        return event.message.chat if event.message else None
    return event.chat if isinstance(event, Message) else None


class ActivityMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        token = _current.set({})
        try:
            result = await handler(event, data)
            marked = _current.get() or {}
        finally:
            _current.reset(token)

        chat = _chat_of(event)
        if chat is None or chat.type != ChatType.PRIVATE:
            # Group traffic is the card's business and is already visible in the group.
            return result

        employee: Employee | None = marked.get("employee") or data.get("employee")
        if employee is None:
            return result

        session: AsyncSession | None = data.get("session")
        if session is None:
            return result

        action = marked.get("action")
        target = marked.get("target")
        if not action:
            action, target = _generic(event)

        await record(
            session, action=action, source=SOURCE_BOT, employee=employee, target=target
        )
        return result
