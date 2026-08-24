"""Answering a notification by replying to it.

The bot sends "RTM wrote to you about RTM-000123"; the natural response is to hold that
message and type back. Before this, that reply reached no one: the bot saw an ordinary
message with no conversation state and answered "I didn't understand", so the most obvious
way to reply was the only one that did not work. Every notification is now linked to its
request, and this router turns those replies into real thread messages.

Works in both directions. The reporter replying to an update reaches the assignee; a
staffer replying to "the reporter wrote" reaches the reporter.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.types import Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.assignments import is_assigned
from afu_shared.enums import MessageVisibility
from afu_shared.models import Employee, Request
from app.filters.media import HAS_MEDIA
from app.filters.replies import RepliedRequest
from app.services.thread import store_thread_message
from app.utils.transient import send_transient

logger = logging.getLogger(__name__)

router = Router(name="replies")


@router.message(RepliedRequest(), F.text | HAS_MEDIA)
async def reply_to_notification(
    message: Message,
    linked_request_id: int,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    request = await session.get(Request, linked_request_id)
    if request is None:
        return

    is_requester = request.requester_employee_id == employee.id
    is_staff = employee.is_rtm_staff and await is_assigned(
        session, request.id, employee.id
    )
    if not (is_requester or is_staff):
        # Somebody replying to a notification about a request that is no longer theirs —
        # they left the job, or the link outlived their involvement.
        await send_transient(
            bot, redis, arq_pool, message.chat.id,
            "Bu murojaat endi sizga tegishli emas.",
        )
        return

    row, _ = await store_thread_message(
        session, bot, message,
        request_id=request.id,
        employee_id=employee.id,
        # Always the visible side. An internal RTM note is a deliberate act taken from the
        # request screen; nobody means one by replying to a message in their chat.
        visibility=MessageVisibility.TO_REQUESTER,
    )

    # Commit before queueing: the worker reads the message back by id in its own session.
    await session.commit()
    await arq_pool.enqueue_job(
        "notify_request_message", request.id, employee.id, row.id
    )

    await send_transient(
        bot, redis, arq_pool, message.chat.id,
        f"✅ Javobingiz <b>{request.display_number}</b> bo'yicha yuborildi.",
    )
