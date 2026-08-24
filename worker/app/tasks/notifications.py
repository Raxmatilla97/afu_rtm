import logging

from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from sqlalchemy import select

from afu_shared.db import session_scope
from afu_shared.enums import MessageVisibility
from afu_shared.models import Employee, Request, RequestMessage
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


async def notify_request_message(ctx: dict, request_id: int, author_employee_id: int) -> None:
    """Deliver the newest message on a request to whoever should see it.

    Both directions route through here so requester->staff and staff->requester share one
    notification path rather than drifting apart.
    """
    async with session_scope() as session:
        request = await session.get(Request, request_id)
        if request is None:
            logger.error("notify_request_message: request %s not found", request_id)
            return

        message = (
            await session.execute(
                select(RequestMessage)
                .where(RequestMessage.request_id == request_id)
                .order_by(RequestMessage.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if message is None:
            return

        author = await session.get(Employee, author_employee_id)
        author_name = author.full_name if author else "—"
        display_number = request.display_number
        body = message.body
        internal = message.visibility == MessageVisibility.INTERNAL.value

        if internal:
            # Internal notes go to the other RTM staff, never to the requester.
            recipients = list(
                (
                    await session.execute(
                        select(Employee).where(
                            Employee.is_rtm_staff.is_(True),
                            Employee.telegram_user_id.isnot(None),
                            Employee.id != author_employee_id,
                        )
                    )
                ).scalars()
            )
            text = f"🗂 <b>[Ichki] {display_number}</b> — {author_name}:\n\n{body}"
        elif author_employee_id == request.requester_employee_id:
            # Requester wrote: tell the assignee, or all staff if nobody is assigned yet.
            if request.assigned_to_employee_id:
                assignee = await session.get(Employee, request.assigned_to_employee_id)
                recipients = [assignee] if assignee and assignee.telegram_user_id else []
            else:
                recipients = list(
                    (
                        await session.execute(
                            select(Employee).where(
                                Employee.is_rtm_staff.is_(True),
                                Employee.telegram_user_id.isnot(None),
                            )
                        )
                    ).scalars()
                )
            text = f"💬 <b>{display_number}</b> — murojaatchi {author_name}:\n\n{body}"
        else:
            requester = await session.get(Employee, request.requester_employee_id)
            recipients = [requester] if requester and requester.telegram_user_id else []
            text = f"💬 <b>{display_number}</b> bo'yicha RTM xabari:\n\n{body}"

        targets = [r.telegram_user_id for r in recipients if r and r.telegram_user_id]

    bot = get_bot()
    for chat_id in targets:
        try:
            await bot.send_message(chat_id, text, parse_mode="HTML")
        except TelegramForbiddenError:
            logger.warning("Cannot deliver request message to %s: bot blocked", chat_id)
