from aiogram import F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import MessageVisibility
from afu_shared.models import Employee, Request, RequestMessage
from app.states.staff_actions import StaffActionStates

router = Router(name="messaging")


@router.message(StaffActionStates.awaiting_message_to_requester, F.text)
async def send_message_to_requester(
    message: Message, state: FSMContext, session: AsyncSession, employee: Employee
) -> None:
    data = await state.get_data()
    request_id = data["request_id"]
    request = await session.get(Request, request_id)
    await state.clear()

    if not request or request.assigned_to_employee_id != employee.id:
        await message.answer("Topilmadi.")
        return

    body = message.text.strip()
    session.add(
        RequestMessage(
            request_id=request.id,
            author_employee_id=employee.id,
            visibility=MessageVisibility.TO_REQUESTER.value,
            body=body,
        )
    )
    await session.flush()

    requester = await session.get(Employee, request.requester_employee_id)
    if requester and requester.telegram_user_id:
        try:
            await message.bot.send_message(
                requester.telegram_user_id,
                f"💬 {request.display_number} bo'yicha RTM xabari:\n\n{body}",
            )
        except TelegramForbiddenError:
            pass

    await message.answer("Xabar yuborildi.")


@router.message(StaffActionStates.awaiting_internal_message, F.text)
async def send_internal_message(
    message: Message, state: FSMContext, session: AsyncSession, employee: Employee
) -> None:
    data = await state.get_data()
    request_id = data["request_id"]
    request = await session.get(Request, request_id)
    await state.clear()

    if not request:
        await message.answer("Topilmadi.")
        return

    body = message.text.strip()
    session.add(
        RequestMessage(
            request_id=request.id,
            author_employee_id=employee.id,
            visibility=MessageVisibility.INTERNAL.value,
            body=body,
        )
    )
    await session.flush()

    other_staff = (
        await session.execute(
            select(Employee).where(
                Employee.is_rtm_staff.is_(True),
                Employee.telegram_user_id.is_not(None),
                Employee.id != employee.id,
            )
        )
    ).scalars()

    text = f"🗂 [Ichki] {request.display_number} — {employee.full_name}:\n\n{body}"
    for staff in other_staff:
        try:
            await message.bot.send_message(staff.telegram_user_id, text)
        except TelegramForbiddenError:
            continue

    await message.answer("Ichki izoh saqlandi va boshqa RTM xodimlariga yuborildi.")
