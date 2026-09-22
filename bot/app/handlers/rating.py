"""Legacy rating buttons.

The completion notification used to carry ``rate:{rid}:{score}`` buttons. Notifications
already sitting in users' chats still do, so this handler stays for one release; new
notifications use the ReqCB factory and are handled in ``handlers/my_requests.py``.
"""

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from arq import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.assignments import assignee_ids
from afu_shared.enums import RequestStatus
from afu_shared.models import Employee, Rating, Request

logger = logging.getLogger(__name__)

router = Router(name="rating_legacy")


@router.callback_query(F.data.startswith("rate:"))
async def legacy_rate(
    callback: CallbackQuery,
    session: AsyncSession,
    employee: Employee,
    arq_pool: ArqRedis,
) -> None:
    try:
        _, raw_rid, raw_score = callback.data.split(":")
        rid, score = int(raw_rid), int(raw_score)
    except (ValueError, AttributeError):
        await callback.answer()
        return

    if not 1 <= score <= 5:
        await callback.answer()
        return

    request = await session.get(Request, rid)
    if request is None or request.requester_employee_id != employee.id:
        await callback.answer("Bu murojaat sizga tegishli emas.", show_alert=True)
        return
    if request.status != RequestStatus.COMPLETED.value:
        await callback.answer("Murojaat hali bajarilmagan.", show_alert=True)
        return

    targets = await assignee_ids(session, rid)
    if not targets:
        await callback.answer("Bu murojaat hech kimga tayinlanmagan.", show_alert=True)
        return

    existing = (
        await session.execute(select(Rating).where(Rating.request_id == rid).limit(1))
    ).scalar_one_or_none()
    if existing is not None:
        await callback.answer("Siz allaqachon baholagansiz.", show_alert=True)
        return

    session.add_all(
        Rating(
            request_id=rid,
            rated_employee_id=target_id,
            rated_by_employee_id=employee.id,
            score=score,
        )
        for target_id in targets
    )
    await session.flush()
    # Committed here rather than left to the middleware: the two jobs below are picked up by
    # a worker with its own session, which would otherwise find no rating to announce.
    await session.commit()
    await arq_pool.enqueue_job("refresh_request_cards", rid)
    await arq_pool.enqueue_job("notify_request_rated", rid)

    if callback.message and callback.message.text:
        await callback.message.edit_text(
            callback.message.text
            + f"\n\n⭐ Bahoyingiz: {score}/5. Rahmat! Bajargan xodimlarga xabar berildi."
        )
    await callback.answer("Rahmat!")
