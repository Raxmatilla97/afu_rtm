"""Blocks unauthenticated users centrally.

Previously every handler repeated its own eligibility check, and the callback handlers
declared ``employee: Employee`` as non-optional — so a stale button pressed by someone who
was never verified reached a handler that assumed they were. Guarding in one place removes
that whole class of bug and keeps the per-screen code focused on its own job.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.callbacks import QuickCB
from app.middlewares.identity import AuthState
from app.states.quick_login import QuickLoginStates

#: What a group member sees when they press a card button without having onboarded. The
#: fix is always the same and always in a DM, so the alert says exactly that.
GROUP_NOT_ONBOARDED = (
    "Avval botga shaxsan kiring: botni oching, /start bosing va HEMIS orqali "
    "ro'yxatdan o'ting."
)

#: A blocked person is not missing a step, so telling them to go and register would send
#: them round a loop that cannot end.
GROUP_BLOCKED = "🚫 Siz botdan foydalana olmaysiz — hisobingiz bloklangan."

#: Commands that must work before the user is fully onboarded.
#:
#: Short on purpose. Every other handler declares ``employee: Employee`` as non-optional,
#: so letting ``/menu`` or ``/help`` through for an unonboarded user meant the handler ran
#: with ``employee=None`` and died on ``employee.full_name`` — from the chat that looked
#: exactly like the bot ignoring the command. Anything not listed here falls through to the
#: onboarding screen, which is the useful answer anyway.
#:
#: ``/chiqish`` is here because being half-logged-in is exactly when somebody needs it:
#: linked to the wrong employee, or stuck before the phone share. Its handler accepts a
#: missing employee.
_ALLOWED_COMMANDS = ("/start", "/chiqish")


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

        # The quick login happens entirely inside this guard's "not allowed yet" territory:
        # its buttons are pressed and its answers are typed by people who are, by
        # definition, not signed in. Blocking them would make the only working door
        # unopenable. A blocked account is still refused below, one branch further down.
        if auth_state is not AuthState.INELIGIBLE and await _is_quick_login_step(event, data):
            return await handler(event, data)

        # Not onboarded: short-circuit to the screen that explains what is missing,
        # rather than letting the handler run with a missing or ineligible employee.
        from app.screens.auth import show_auth_screen

        # Onboarding is a private conversation — it asks for a HEMIS login and a phone
        # number. Pushing that into a group would be both useless and a privacy problem.
        if _is_group(event):
            if isinstance(event, CallbackQuery):
                # A pop-up only the presser sees, pointing at the one place this can be
                # fixed. Nothing is posted into the shared chat.
                employee = data.get("employee")
                blocked = employee is not None and employee.is_blocked
                await event.answer(
                    GROUP_BLOCKED if blocked else GROUP_NOT_ONBOARDED, show_alert=True
                )
                return None
            # Group messages run on: the only handlers that can see them belong to the
            # group router, every one of them checks RTM membership itself, and they all
            # accept a missing employee. Blocking here would instead make /rtm_on answer
            # with silence for exactly the person who needs to be told why.
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer()
            chat_id = event.message.chat.id if event.message else None
        else:
            chat_id = event.chat.id if isinstance(event, Message) else None

        if chat_id is not None:
            # A typed message lands below the anchor, so the screen has to move down to
            # stay visible. A button press is already on the anchor itself — moving it
            # there would just make the screen jump around under the user's finger.
            await show_auth_screen(
                chat_id=chat_id, data=data, force_new=isinstance(event, Message)
            )
        return None


async def _is_quick_login_step(event: TelegramObject, data: dict[str, Any]) -> bool:
    """A button or an answer belonging to the quick-login conversation."""
    if isinstance(event, CallbackQuery):
        prefix = f"{QuickCB.__prefix__}{QuickCB.__separator__}"
        return (event.data or "").startswith(prefix)
    if isinstance(event, Message):
        state = data.get("state")
        if state is None:
            return False
        current = await state.get_state()
        return bool(current) and str(current).startswith(f"{QuickLoginStates.__name__}:")
    return False


def _chat_of(event: TelegramObject):
    if isinstance(event, CallbackQuery):
        return event.message.chat if event.message else None
    return event.chat if isinstance(event, Message) else None


def _is_group(event: TelegramObject) -> bool:
    chat = _chat_of(event)
    return chat is not None and chat.type != ChatType.PRIVATE


def _is_always_allowed(event: TelegramObject) -> bool:
    if isinstance(event, Message):
        # The contact share is how onboarding finishes, so it must never be blocked.
        if event.contact is not None:
            return True
        text = (event.text or "").strip().lower()
        return any(text.startswith(cmd) for cmd in _ALLOWED_COMMANDS)
    return False
