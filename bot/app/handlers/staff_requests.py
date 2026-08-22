from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from arq import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import RequestStatus
from afu_shared.models import Employee, Request, RequestStatusHistory
from app.keyboards.common import BTN_MY_ASSIGNMENTS
from app.keyboards.requests import assignment_list_keyboard, request_detail_keyboard
from app.states.staff_actions import StaffActionStates
from app.utils.transient import schedule_delete

router = Router(name="staff_requests")


def _require_staff(employee: Employee | None) -> bool:
    return employee is not None and employee.is_eligible and employee.is_rtm_staff


async def _render_list(session: AsyncSession, employee: Employee) -> tuple[str, InlineKeyboardMarkup]:
    requests = list(
        (
            await session.execute(
                select(Request)
                .where(
                    Request.assigned_to_employee_id == employee.id,
                    Request.status.in_([RequestStatus.ASSIGNED.value, RequestStatus.IN_PROGRESS.value]),
                )
                .order_by(Request.deadline_at.is_(None), Request.deadline_at)
            )
        ).scalars()
    )
    text = f"🛠 Sizga tayinlangan topshiriqlar: {len(requests)} ta"
    return text, assignment_list_keyboard(requests)


@router.message(F.text == BTN_MY_ASSIGNMENTS)
async def show_assignments(
    message: Message, session: AsyncSession, employee: Employee | None, arq_pool: ArqRedis
) -> None:
    await schedule_delete(arq_pool, message.chat.id, message.message_id)

    if not _require_staff(employee):
        await message.answer("Bu bo'lim faqat RTM xodimlari uchun.")
        return
    text, keyboard = await _render_list(session, employee)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "req_back")
async def back_to_list(callback: CallbackQuery, session: AsyncSession, employee: Employee) -> None:
    text, keyboard = await _render_list(session, employee)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("req:"))
async def open_request(callback: CallbackQuery, session: AsyncSession, employee: Employee) -> None:
    request_id = int(callback.data.removeprefix("req:"))
    request = await session.get(Request, request_id)
    if not request or request.assigned_to_employee_id != employee.id:
        await callback.answer("Topilmadi", show_alert=True)
        return

    requester = await session.get(Employee, request.requester_employee_id)
    deadline = request.deadline_at.strftime("%d.%m.%Y %H:%M") if request.deadline_at else "belgilanmagan"
    text = (
        f"№ {request.display_number}\n"
        f"Kategoriya: {request.category.label_uz if request.category else '-'}\n"
        f"Murojaatchi: {requester.full_name if requester else '-'}\n"
        f"Muddat: {deadline}\n"
        f"Holat: {request.status}\n\n"
        f"Tavsif:\n{request.description}"
    )
    await callback.message.edit_text(text, reply_markup=request_detail_keyboard(request))
    await callback.answer()


@router.callback_query(F.data.startswith("req_start:"))
async def start_request(callback: CallbackQuery, session: AsyncSession, employee: Employee) -> None:
    request_id = int(callback.data.removeprefix("req_start:"))
    request = await session.get(Request, request_id)
    if not request or request.assigned_to_employee_id != employee.id:
        await callback.answer("Topilmadi", show_alert=True)
        return

    old_status = request.status
    request.status = RequestStatus.IN_PROGRESS.value
    session.add(
        RequestStatusHistory(
            request_id=request.id,
            from_status=old_status,
            to_status=request.status,
            changed_by_employee_id=employee.id,
        )
    )
    await session.flush()
    await callback.message.edit_text(
        f"▶️ {request.display_number} ish jarayoniga o'tkazildi.", reply_markup=request_detail_keyboard(request)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("req_complete:"))
async def ask_completion_note(callback: CallbackQuery, state: FSMContext) -> None:
    request_id = int(callback.data.removeprefix("req_complete:"))
    await state.update_data(request_id=request_id)
    await state.set_state(StaffActionStates.awaiting_completion_note)
    await callback.message.edit_text("Bajarilgan ish haqida qisqacha izoh yozing:")
    await callback.answer()


@router.message(StaffActionStates.awaiting_completion_note, F.text)
async def complete_request(
    message: Message, state: FSMContext, session: AsyncSession, employee: Employee, arq_pool: ArqRedis
) -> None:
    data = await state.get_data()
    request_id = data["request_id"]
    request = await session.get(Request, request_id)
    await state.clear()

    if not request or request.assigned_to_employee_id != employee.id:
        await message.answer("Topilmadi.")
        return

    old_status = request.status
    request.status = RequestStatus.COMPLETED.value
    request.completed_at = datetime.now(timezone.utc)
    request.completion_note = message.text.strip()
    session.add(
        RequestStatusHistory(
            request_id=request.id,
            from_status=old_status,
            to_status=request.status,
            changed_by_employee_id=employee.id,
        )
    )
    await session.flush()

    await arq_pool.enqueue_job("send_completion_notification", request.id)
    await message.answer(f"✅ {request.display_number} bajarildi deb belgilandi. Murojaatchiga xabar yuborildi.")


@router.callback_query(F.data.startswith("req_msg:"))
async def ask_message_to_requester(callback: CallbackQuery, state: FSMContext) -> None:
    request_id = int(callback.data.removeprefix("req_msg:"))
    await state.update_data(request_id=request_id)
    await state.set_state(StaffActionStates.awaiting_message_to_requester)
    await callback.message.edit_text("Murojaatchiga yuboriladigan xabar matnini kiriting:")
    await callback.answer()


@router.callback_query(F.data.startswith("req_internal:"))
async def ask_internal_message(callback: CallbackQuery, state: FSMContext) -> None:
    request_id = int(callback.data.removeprefix("req_internal:"))
    await state.update_data(request_id=request_id)
    await state.set_state(StaffActionStates.awaiting_internal_message)
    await callback.message.edit_text("RTM hodimlari uchun ichki izoh matnini kiriting:")
    await callback.answer()
