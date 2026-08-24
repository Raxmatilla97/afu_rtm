from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Employee


class AuthState(StrEnum):
    #: No employee row is linked to this Telegram account.
    ANONYMOUS = "anonymous"
    #: HEMIS login done, but the contact share (and so the verified phone) is still missing.
    OAUTH_ONLY = "oauth_only"
    #: Linked, phone-verified and currently employed.
    READY = "ready"
    #: Linked, but no longer allowed in (left the university, status changed).
    INELIGIBLE = "ineligible"


class IdentityMiddleware(BaseMiddleware):
    """Injects ``employee`` and the derived ``auth_state`` into handler data."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session: AsyncSession = data["session"]
        telegram_user = getattr(event, "from_user", None)

        employee: Employee | None = None
        if telegram_user is not None:
            employee = (
                await session.execute(
                    select(Employee).where(Employee.telegram_user_id == telegram_user.id)
                )
            ).scalar_one_or_none()

        data["employee"] = employee
        data["auth_state"] = _classify(employee)
        return await handler(event, data)


def _classify(employee: Employee | None) -> AuthState:
    if employee is None:
        return AuthState.ANONYMOUS
    if not employee.is_eligible:
        return AuthState.INELIGIBLE
    if employee.verified_at is None:
        return AuthState.OAUTH_ONLY
    return AuthState.READY
