"""Requester-side handlers: open a request, read the thread, reply, rate."""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.assignments import assignee_ids
from afu_shared.enums import MessageVisibility, RequestStatus
from afu_shared.media import send_attachments
from afu_shared.models import Employee, Rating, Request
from app.callbacks import ReqCB
from app.filters.media import HAS_MEDIA
from app.screens import my_requests as screens
from app.services.attachments import attachments_for_request
from app.services.thread import store_thread_message
from app.states.staff_actions import RequesterStates
from app.ui.anchor import render
from app.utils.transient import send_transient, track_media

router = Router(name="my_requests")


@router.callback_query(ReqCB.filter(F.act == "open"))
async def open_request(
    callback: CallbackQuery,
    callback_data: ReqCB,
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
        await callback.answer("Murojaat topilmadi.", show_alert=True)
        return
    await render(bot, redis, callback.message.chat.id, screen)


@router.callback_query(ReqCB.filter(F.act == "thread"))
async def open_thread(
    callback: CallbackQuery,
    callback_data: ReqCB,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    # `score` carries the list page here so returning from the thread lands on the right page.
    list_page = callback_data.score or 1
    screen = await screens.build_thread(
        session, employee, callback_data.rid, callback_data.page, list_page
    )
    if screen is None:
        await callback.answer("Murojaat topilmadi.", show_alert=True)
        return
    await render(bot, redis, callback.message.chat.id, screen)


@router.callback_query(ReqCB.filter(F.act == "reply"))
async def ask_reply(
    callback: CallbackQuery,
    callback_data: ReqCB,
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

    request = await session.get(Request, callback_data.rid)
    if request is None or request.requester_employee_id != employee.id:
        await callback.answer("Murojaat topilmadi.", show_alert=True)
        return

    await state.set_state(RequesterStates.awaiting_reply_body)
    await state.update_data(rid=callback_data.rid, page=callback_data.page)
    await send_transient(
        bot, redis, arq_pool, callback.message.chat.id,
        f"✍️ {request.display_number} bo'yicha xabaringizni yuboring.\n"
        "Yozishingiz yoki ovozli xabar, video, rasm jo'natishingiz mumkin.",
        ttl=180,
    )


@router.message(RequesterStates.awaiting_reply_body, F.text | HAS_MEDIA)
async def submit_reply(
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
    if request is None or request.requester_employee_id != employee.id:
        await state.clear()
        return

    row, _ = await store_thread_message(
        session, bot, message,
        request_id=rid,
        employee_id=employee.id,
        visibility=MessageVisibility.TO_REQUESTER,
    )
    await state.clear()

    # Commit before queueing. The worker looks the message up by id in its own session, and
    # it is fast enough to get there before this handler returns and the session middleware
    # commits — at which point it would find nothing and deliver nothing.
    await session.commit()

    # Notify RTM through the worker, which owns the Bot client for outbound DMs.
    await arq_pool.enqueue_job("notify_request_message", rid, employee.id, row.id)

    screen = await screens.build_detail(session, employee, rid, page)
    if screen:
        await render(bot, redis, message.chat.id, screen, force_new=True)
    await send_transient(bot, redis, arq_pool, message.chat.id, "✅ Xabaringiz yuborildi.")


@router.callback_query(ReqCB.filter(F.act == "files"))
async def resend_files(
    callback: CallbackQuery,
    callback_data: ReqCB,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
) -> None:
    """Send the requester every file on their request — theirs and RTM's replies alike.

    Internal RTM notes are excluded at the query, not here: see
    ``attachments_for_request(include_internal=False)``.
    """
    await callback.answer()
    if callback.message is None:
        return

    request = await session.get(Request, callback_data.rid)
    if request is None or request.requester_employee_id != employee.id:
        await callback.answer("Murojaat topilmadi.", show_alert=True)
        return

    files = await attachments_for_request(session, request.id, include_internal=False)
    if not files:
        await callback.answer("Bu murojaatda fayl yo'q.", show_alert=True)
        return

    sent = await send_attachments(
        bot, callback.message.chat.id, files,
        caption=f"📎 <b>{request.display_number}</b> — materiallar",
    )
    # Tracked so the next screen change sweeps them away.
    await track_media(redis, callback.message.chat.id, sent)

    screen = await screens.build_detail(session, employee, request.id, callback_data.page)
    if screen:
        await render(
            bot, redis, callback.message.chat.id, screen, force_new=True, keep_media=True
        )


@router.callback_query(ReqCB.filter(F.act == "rate"))
async def ask_rating(
    callback: CallbackQuery,
    callback_data: ReqCB,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    request = await session.get(Request, callback_data.rid)
    if request is None or request.requester_employee_id != employee.id:
        await callback.answer("Murojaat topilmadi.", show_alert=True)
        return

    await render(
        bot, redis, callback.message.chat.id,
        screens.build_rating_screen(callback_data.rid, callback_data.page, request.display_number),
    )


@router.callback_query(ReqCB.filter(F.act == "rate_set"))
async def set_rating(
    callback: CallbackQuery,
    callback_data: ReqCB,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    request = await session.get(Request, callback_data.rid)
    if request is None or request.requester_employee_id != employee.id:
        await callback.answer("Murojaat topilmadi.", show_alert=True)
        return
    if request.status != RequestStatus.COMPLETED.value:
        await callback.answer("Murojaat hali bajarilmagan.", show_alert=True)
        return

    targets = await assignee_ids(session, request.id)
    if not targets:
        await callback.answer("Bu murojaat hech kimga tayinlanmagan.", show_alert=True)
        return

    existing = (
        await session.execute(select(Rating).where(Rating.request_id == request.id).limit(1))
    ).scalar_one_or_none()
    if existing is not None:
        await callback.answer("Siz allaqachon baholagansiz.", show_alert=True)
        return

    # One score per person who worked on it: the requester rates the service, and everyone
    # who delivered it should carry that score on their record.
    session.add_all(
        Rating(
            request_id=request.id,
            rated_employee_id=target_id,
            rated_by_employee_id=employee.id,
            score=callback_data.score,
        )
        for target_id in targets
    )
    await session.flush()
    await session.commit()
    await arq_pool.enqueue_job("refresh_request_cards", request.id)
    # The people who did the work are told. Before this the score reached the leaderboard
    # and the group card and stopped there — the staffer it was about heard nothing.
    await arq_pool.enqueue_job("notify_request_rated", request.id)

    # One tap, committed immediately, and no follow-up question. A comment step here would
    # be a second screen the reporter can simply walk away from, and the notification would
    # then either go out without the comment or not go out at all. Anyone who wants to say
    # more has the "💬 Yozish" button on the screen below — it reaches the same people and
    # it already works.
    screen = await screens.build_detail(session, employee, request.id, callback_data.page)
    if screen:
        await render(bot, redis, callback.message.chat.id, screen)
    await send_transient(
        bot, redis, arq_pool, callback.message.chat.id,
        f"⭐ Bahoyingiz uchun rahmat! ({callback_data.score}/5)\n"
        "Bajargan xodimlarga xabar berildi. Qo'shimcha izoh yozmoqchi bo'lsangiz — "
        "«💬 Yozish» tugmasini bosing.",
        ttl=120,
    )
