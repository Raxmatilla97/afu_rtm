"""Blocks unauthenticated users centrally.

Previously every handler repeated its own eligibility check, and the callback handlers
declared ``employee: Employee`` as non-optional — so a stale button pressed by someone who
was never verified reached a handler that assumed they were. Guarding in one place removes
that whole class of bug and keeps the per-screen code focused on its own job.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.middlewares.identity import AuthState

#: Commands that must work before the user is fully onboarded.
_ALLOWED_COMMANDS = ("/start", "/help", "/menu", "/cancel")


class AuthGuardMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        auth_state: AuthState = data["auth_state"]
        if auth_state is AuthState.READY:
            return await handler(event, data)

        if _is_always_allowed(event):
            return await handler(event, data)

        # Not onboarded: short-circuit to the screen that explains what is missing,
        # rather than letting the handler run with a missing or ineligible employee.
        from app.screens.auth import show_auth_screen

        if isinstance(event, CallbackQuery):
            await event.answer()
            chat_id = event.message.chat.id if event.message else None
        else:
            chat_id = event.chat.id if isinstance(event, Message) else None

        if chat_id is not None:
            await show_auth_screen(chat_id=chat_id, data=data)
        return None


def _is_always_allowed(event: TelegramObject) -> bool:
    if isinstance(event, Message):
        # The contact share is how onboarding finishes, so it must never be blocked.
        if event.contact is not None:
            return True
        text = (event.text or "").strip().lower()
        return any(text.startswith(cmd) for cmd in _ALLOWED_COMMANDS)
    return False
