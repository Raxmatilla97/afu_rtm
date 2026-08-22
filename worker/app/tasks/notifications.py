import logging

from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from afu_shared.db import session_scope
from afu_shared.models import Employee, Request
from app.bot_client import get_bot

logger = logging.getLogger(__name__)


def _rating_keyboard(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=str(score), callback_data=f"rate:{request_id}:{score}")
                for score in range(1, 6)
            ]
        ]
    )


async def send_completion_notification(ctx: dict, request_id: int) -> None:
    async with session_scope() as session:
        request = await session.get(Request, request_id)
        if request is None:
            logger.error("send_completion_notification: request %s not found", request_id)
            return

        requester = await session.get(Employee, request.requester_employee_id)
        staff = (
            await session.get(Employee, request.assigned_to_employee_id)
            if request.assigned_to_employee_id
            else None
        )
        if not requester or not requester.telegram_user_id:
            return

        staff_name = staff.full_name if staff else "RTM xodimi"
        text = (
            f"✅ Murojaatingiz bajarildi!\n\n"
            f"№ {request.display_number}\n"
            f"Tavsif: {request.description}\n"
            f"Bajardi: {staff_name}\n"
            f"Izoh: {request.completion_note or '-'}\n\n"
            f"Xizmat sifatini baholang:"
        )

        bot = get_bot()
        try:
            await bot.send_message(
                requester.telegram_user_id, text, reply_markup=_rating_keyboard(request.id)
            )
        except TelegramForbiddenError:
            logger.warning("Cannot notify requester %s: bot blocked", requester.telegram_user_id)
