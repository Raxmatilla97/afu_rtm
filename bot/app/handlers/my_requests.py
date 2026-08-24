"""Requester-side handlers: open a request, read the thread, reply, rate."""

from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import MessageVisibility, RequestStatus
from afu_shared.models import Employee, Rating, Request, RequestMessage
from app.callbacks import ReqCB
from app.screens import my_requests as screens
from app.states.staff_actions import RequesterStates
from app.ui.anchor import render
from app.utils.transient import send_transient

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
        f"✍️ {request.display_number} bo'yicha xabaringizni yozing:",
        ttl=120,
    )


@router.message(RequesterStates.awaiting_reply_body, F.text)
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

    session.add(
        RequestMessage(
            request_id=rid,
            author_employee_id=employee.id,
            visibility=MessageVisibility.TO_REQUESTER.value,
            body=(message.text or "").strip(),
        )
    )
    await session.flush()
    await state.clear()

    # Notify RTM through the worker, which owns the Bot client for outbound DMs.
    await arq_pool.enqueue_job("notify_request_message", rid, employee.id)

    screen = await screens.build_detail(session, employee, rid, page)
    if screen:
        await render(bot, redis, message.chat.id, screen)
    await send_transient(bot, redis, arq_pool, message.chat.id, "✅ Xabaringiz yuborildi.")


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
    if request.assigned_to_employee_id is None:
        await callback.answer("Bu murojaat hech kimga tayinlanmagan.", show_alert=True)
        return

    existing = (
        await session.execute(select(Rating).where(Rating.request_id == request.id))
    ).scalar_one_or_none()
    if existing is not None:
        await callback.answer("Siz allaqachon baholagansiz.", show_alert=True)
        return

    session.add(
        Rating(
            request_id=request.id,
            rated_employee_id=request.assigned_to_employee_id,
            rated_by_employee_id=employee.id,
            score=callback_data.score,
        )
    )
    await session.flush()

    screen = await screens.build_detail(session, employee, request.id, callback_data.page)
    if screen:
        await render(bot, redis, callback.message.chat.id, screen)
    await send_transient(
        bot, redis, arq_pool, callback.message.chat.id,
        f"⭐ Bahoyingiz uchun rahmat! ({callback_data.score}/5)",
    )
