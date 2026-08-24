"""Staff-authored messages: to the requester, and internal RTM notes."""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import MessageVisibility
from afu_shared.models import Employee, Request, RequestMessage
from app.screens import assignments as screens
from app.states.staff_actions import StaffActionStates
from app.ui.anchor import render
from app.utils.transient import send_transient

router = Router(name="messaging")


async def _store(
    session: AsyncSession,
    state: FSMContext,
    employee: Employee,
    body: str,
    visibility: MessageVisibility,
) -> tuple[Request, int] | None:
    data = await state.get_data()
    rid, page = data["rid"], data.get("page", 1)

    request = await session.get(Request, rid)
    if request is None or request.assigned_to_employee_id != employee.id:
        return None

    session.add(
        RequestMessage(
            request_id=rid,
            author_employee_id=employee.id,
            visibility=visibility.value,
            body=body,
        )
    )
    await session.flush()
    return request, page


@router.message(StaffActionStates.awaiting_message_to_requester, F.text)
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
        session, state, employee, (message.text or "").strip(), MessageVisibility.TO_REQUESTER
    )
    await state.clear()
    if result is None:
        return
    request, page = result

    # Delivery goes through the worker so both directions share one notification path.
    await arq_pool.enqueue_job("notify_request_message", request.id, employee.id)

    screen = await screens.build_detail(session, employee, request.id, page)
    if screen:
        await render(bot, redis, message.chat.id, screen)
    await send_transient(bot, redis, arq_pool, message.chat.id, "✅ Xabar yuborildi.")


@router.message(StaffActionStates.awaiting_internal_message, F.text)
async def internal_note(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    result = await _store(
        session, state, employee, (message.text or "").strip(), MessageVisibility.INTERNAL
    )
    await state.clear()
    if result is None:
        return
    request, page = result

    await arq_pool.enqueue_job("notify_request_message", request.id, employee.id)

    screen = await screens.build_detail(session, employee, request.id, page)
    if screen:
        await render(bot, redis, message.chat.id, screen)
    await send_transient(
        bot, redis, arq_pool, message.chat.id, "🗂 Ichki izoh saqlandi."
    )
