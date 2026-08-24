"""Staff-authored messages: to the requester, and internal RTM notes.

Both accept text, a voice note, a video, a round video or a file — an RTM staffer walking
between buildings should be able to answer by holding the microphone button, and "look at
this" is often better shown than written.
"""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import MessageVisibility
from afu_shared.models import Employee, Request, RequestMessage
from app.filters.media import HAS_MEDIA
from app.screens import assignments as screens
from app.services.thread import store_thread_message
from app.states.staff_actions import StaffActionStates
from app.ui.anchor import render
from app.utils.transient import send_transient

router = Router(name="messaging")

ACCEPTS_CONTENT = F.text | HAS_MEDIA


async def _store(
    session: AsyncSession,
    bot: Bot,
    message: Message,
    state: FSMContext,
    employee: Employee,
    visibility: MessageVisibility,
) -> tuple[Request, int, RequestMessage] | None:
    data = await state.get_data()
    rid, page = data["rid"], data.get("page", 1)

    request = await session.get(Request, rid)
    if request is None or request.assigned_to_employee_id != employee.id:
        return None

    row, _ = await store_thread_message(
        session, bot, message,
        request_id=rid,
        employee_id=employee.id,
        visibility=visibility,
    )
    return request, page, row


@router.message(StaffActionStates.awaiting_message_to_requester, ACCEPTS_CONTENT)
async def message_to_requester(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    result = await _store(
        session, bot, message, state, employee, MessageVisibility.TO_REQUESTER
    )
    await state.clear()
    if result is None:
        return
    request, page, row = result

    # Commit before queueing: the worker looks the message up by id in its own session and
    # would otherwise race this handler's own commit and find nothing.
    await session.commit()

    # Delivery goes through the worker so both directions share one notification path.
    await arq_pool.enqueue_job("notify_request_message", request.id, employee.id, row.id)

    screen = await screens.build_detail(session, employee, request.id, page)
    if screen:
        await render(bot, redis, message.chat.id, screen, force_new=True)
    await send_transient(bot, redis, arq_pool, message.chat.id, "✅ Xabar yuborildi.")


@router.message(StaffActionStates.awaiting_internal_message, ACCEPTS_CONTENT)
async def internal_note(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    result = await _store(session, bot, message, state, employee, MessageVisibility.INTERNAL)
    await state.clear()
    if result is None:
        return
    request, page, row = result

    await session.commit()
    await arq_pool.enqueue_job("notify_request_message", request.id, employee.id, row.id)

    screen = await screens.build_detail(session, employee, request.id, page)
    if screen:
        await render(bot, redis, message.chat.id, screen, force_new=True)
    await send_transient(
        bot, redis, arq_pool, message.chat.id, "🗂 Ichki izoh saqlandi."
    )


