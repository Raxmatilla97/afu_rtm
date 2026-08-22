from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Employee


class IdentityMiddleware(BaseMiddleware):
    """Attaches the Employee row (or None) matching the Telegram user to handler data as `employee`."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session: AsyncSession = data["session"]
        telegram_user = getattr(event, "from_user", None)

        employee = None
        if telegram_user is not None:
            employee = (
                await session.execute(
                    select(Employee).where(Employee.telegram_user_id == telegram_user.id)
                )
            ).scalar_one_or_none()

        data["employee"] = employee
        return await handler(event, data)
