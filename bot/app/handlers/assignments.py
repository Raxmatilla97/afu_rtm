"""RTM-staff handlers for assigned requests."""

from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import RequestStatus
from afu_shared.models import Employee, Request, RequestStatusHistory
from app.callbacks import AsgCB
from app.screens import assignments as screens
from app.states.staff_actions import StaffActionStates
from app.ui.anchor import render
from app.utils.transient import send_transient

router = Router(name="assignments")


async def _guard(
    callback: CallbackQuery, session: AsyncSession, employee: Employee, rid: int
) -> Request | None:
    if not employee.is_rtm_staff:
        await callback.answer("Bu bo'lim faqat RTM xodimlari uchun.", show_alert=True)
        return None
    request = await session.get(Request, rid)
    if request is None or request.assigned_to_employee_id != employee.id:
        await callback.answer("Topshiriq topilmadi.", show_alert=True)
        return None
    return request


@router.callback_query(AsgCB.filter(F.act == "open"))
async def open_assignment(
    callback: CallbackQuery,
    callback_data: AsgCB,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.clear()

    screen = await screens.build_detail(session, employee, callback_data.rid, callback_data.page)
    if screen is None:
        await callback.answer("Topshiriq topilmadi.", show_alert=True)
        return
    await render(bot, redis, callback.message.chat.id, screen)


@router.callback_query(AsgCB.filter(F.act == "thread"))
async def open_thread(
    callback: CallbackQuery,
    callback_data: AsgCB,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    screen = await screens.build_thread(
        session, employee, callback_data.rid, callback_data.page, callback_data.page
    )
    if screen is None:
        await callback.answer("Topshiriq topilmadi.", show_alert=True)
        return
    await render(bot, redis, callback.message.chat.id, screen)


@router.callback_query(AsgCB.filter(F.act == "start"))
async def start_work(
    callback: CallbackQuery,
    callback_data: AsgCB,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    request = await _guard(callback, session, employee, callback_data.rid)
    if request is None:
        return

    previous = request.status
    request.status = RequestStatus.IN_PROGRESS.value
    session.add(
        RequestStatusHistory(
            request_id=request.id,
            from_status=previous,
            to_status=request.status,
            changed_by_employee_id=employee.id,
        )
    )
    await session.flush()

    screen = await screens.build_detail(session, employee, request.id, callback_data.page)
    if screen:
        await render(bot, redis, callback.message.chat.id, screen)
    await send_transient(
        bot, redis, arq_pool, callback.message.chat.id,
        f"▶️ {request.display_number} ish jarayoniga o'tkazildi.",
    )


@router.callback_query(AsgCB.filter(F.act == "complete"))
async def ask_completion_note(
    callback: CallbackQuery,
    callback_data: AsgCB,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    request = await _guard(callback, session, employee, callback_data.rid)
    if request is None:
        return

    await state.set_state(StaffActionStates.awaiting_completion_note)
    await state.update_data(rid=request.id, page=callback_data.page)
    await send_transient(
        bot, redis, arq_pool, callback.message.chat.id,
        f"✍️ {request.display_number} — bajarilgan ish haqida qisqacha izoh yozing:",
        ttl=120,
    )


@router.message(StaffActionStates.awaiting_completion_note, F.text)
async def complete_request(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    data = await state.get_data()
    rid, page = data["rid"], data.get("page", 1)

    request = await session.get(Request, rid)
    if request is None or request.assigned_to_employee_id != employee.id:
        await state.clear()
        return

    previous = request.status
    request.status = RequestStatus.COMPLETED.value
    request.completed_at = datetime.now(timezone.utc)
    request.completion_note = (message.text or "").strip()
    session.add(
        RequestStatusHistory(
            request_id=request.id,
            from_status=previous,
            to_status=request.status,
            changed_by_employee_id=employee.id,
            note=request.completion_note,
        )
    )
    await session.flush()
    await state.clear()

    await arq_pool.enqueue_job("send_completion_notification", request.id)

    screen = await screens.build_list(session, employee, page)
    await render(bot, redis, message.chat.id, screen)
    await send_transient(
        bot, redis, arq_pool, message.chat.id,
        f"✅ {request.display_number} bajarildi. Murojaatchiga xabar yuborildi.",
    )


@router.callback_query(AsgCB.filter(F.act == "msg"))
async def ask_message_to_requester(
    callback: CallbackQuery,
    callback_data: AsgCB,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    request = await _guard(callback, session, employee, callback_data.rid)
    if request is None:
        return

    await state.set_state(StaffActionStates.awaiting_message_to_requester)
    await state.update_data(rid=request.id, page=callback_data.page)
    await send_transient(
        bot, redis, arq_pool, callback.message.chat.id,
        f"✍️ {request.display_number} — murojaatchiga yuboriladigan xabarni yozing:",
        ttl=120,
    )


@router.callback_query(AsgCB.filter(F.act == "internal"))
async def ask_internal_note(
    callback: CallbackQuery,
    callback_data: AsgCB,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    request = await _guard(callback, session, employee, callback_data.rid)
    if request is None:
        return

    await state.set_state(StaffActionStates.awaiting_internal_message)
    await state.update_data(rid=request.id, page=callback_data.page)
    await send_transient(
        bot, redis, arq_pool, callback.message.chat.id,
        f"🗂 {request.display_number} — ichki izoh (murojaatchi ko'rmaydi):",
        ttl=120,
    )
