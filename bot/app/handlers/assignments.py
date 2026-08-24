"""RTM-staff handlers for assigned requests."""

from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.assignments import assignee_ids, is_assigned
from afu_shared.enums import MessageVisibility, RequestStatus
from afu_shared.media import describe_attachments, send_attachments
from afu_shared.models import Employee, Request, RequestStatusHistory
from app.callbacks import AsgCB
from app.filters.media import HAS_MEDIA
from app.screens import assignments as screens
from app.services.attachments import attachments_for_request
from app.services.thread import store_thread_message
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
    # Membership, not the primary column: a colleague who joined the job has the same
    # rights on it as whoever picked it up first.
    if request is None or not await is_assigned(session, rid, employee.id):
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

    await session.commit()
    await arq_pool.enqueue_job("refresh_request_cards", request.id)

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
        f"✍️ {request.display_number} — bajarilgan ish haqida hisobot qoldiring.\n"
        "Yozib yuborishingiz, ovozli xabar, video yoki rasm jo'natishingiz mumkin.",
        ttl=180,
    )


@router.message(StaffActionStates.awaiting_completion_note, F.text | HAS_MEDIA)
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
    if request is None or not await is_assigned(session, rid, employee.id):
        await state.clear()
        return

    # The report is stored as a normal thread message so any media it carries hangs off
    # something, and so the requester can read it in the conversation like any other reply.
    # ``completion_note`` keeps the text alone, because that is what the lists and the web
    # interface print.
    row, attachment = await store_thread_message(
        session, bot, message,
        request_id=request.id,
        employee_id=employee.id,
        visibility=MessageVisibility.TO_REQUESTER,
    )

    previous = request.status
    request.status = RequestStatus.COMPLETED.value
    request.completed_at = datetime.now(timezone.utc)
    request.completion_note = row.body or (
        f"{describe_attachments([attachment])} bilan hisobot" if attachment else "Bajarildi"
    )
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

    # Commit before queueing: the worker reads the report back by id in its own session.
    await session.commit()
    await arq_pool.enqueue_job("send_completion_notification", request.id, row.id)

    team = await assignee_ids(session, request.id)
    credited = (
        f" ({len(team)} xodim)" if len(team) > 1 else ""
    )
    await arq_pool.enqueue_job(
        "refresh_request_cards",
        request.id,
        f"✅ <b>{request.display_number}</b> bajarildi — "
        f"<b>{employee.full_name}</b>{credited}.",
    )

    screen = await screens.build_list(session, employee, page)
    await render(bot, redis, message.chat.id, screen, force_new=True)
    await send_transient(
        bot, redis, arq_pool, message.chat.id,
        f"✅ {request.display_number} bajarildi. Murojaatchiga xabar yuborildi.",
    )


@router.callback_query(AsgCB.filter(F.act == "files"))
async def resend_files(
    callback: CallbackQuery,
    callback_data: AsgCB,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
) -> None:
    """Replay every file on the request into the staffer's chat, on demand.

    The assignment notification already pushes them once, but that message scrolls away
    while the job is being worked; being able to pull the evidence back up without
    hunting through the chat is the difference between the bot being usable on site or not.
    """
    await callback.answer()
    if callback.message is None:
        return

    request = await _guard(callback, session, employee, callback_data.rid)
    if request is None:
        return

    files = await attachments_for_request(session, request.id)
    if not files:
        await callback.answer("Bu murojaatda fayl yo'q.", show_alert=True)
        return

    await send_attachments(
        bot, callback.message.chat.id, files,
        caption=f"📎 <b>{request.display_number}</b> — biriktirilgan materiallar",
    )
    # The files land below the anchor, so move the screen back to the bottom.
    screen = await screens.build_detail(session, employee, request.id, callback_data.page)
    if screen:
        await render(bot, redis, callback.message.chat.id, screen, force_new=True)


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
        f"✍️ {request.display_number} — murojaatchiga xabar yuboring.\n"
        "Matn, ovozli xabar, video yoki rasm — barchasi mumkin.",
        ttl=180,
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
        f"🗂 {request.display_number} — ichki izoh (murojaatchi ko'rmaydi).\n"
        "Matn, ovozli xabar yoki fayl yuborishingiz mumkin.",
        ttl=180,
    )
