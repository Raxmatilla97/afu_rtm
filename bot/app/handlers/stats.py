from aiogram import F, Router
from aiogram.types import Message
from arq import ArqRedis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import RequestStatus
from afu_shared.models import Employee, Rating, Request
from app.keyboards.common import BTN_STATS
from app.utils.transient import schedule_delete

router = Router(name="stats")


@router.message(F.text == BTN_STATS)
async def show_stats(
    message: Message, session: AsyncSession, employee: Employee | None, arq_pool: ArqRedis
) -> None:
    await schedule_delete(arq_pool, message.chat.id, message.message_id)

    if employee is None or not employee.is_eligible:
        await message.answer("Avval shaxsingizni tasdiqlashingiz kerak. /start ni bosing.")
        return

    month_expr = func.date_trunc("month", Request.completed_at)
    rows = (
        await session.execute(
            select(month_expr.label("month"), func.count())
            .where(Request.status == RequestStatus.COMPLETED.value)
            .group_by("month")
            .order_by(month_expr.desc())
            .limit(6)
        )
    ).all()

    lines = ["📊 Oylar kesimida bajarilgan murojaatlar:\n"]
    if rows:
        for month, count in rows:
            lines.append(f"{month.strftime('%Y-%m')}: {count} ta")
    else:
        bajarilgan = (
            await session.execute(
                select(func.count()).where(Request.status == RequestStatus.COMPLETED.value)
            )
        ).scalar_one()
        lines.append(f"Hozircha ma'lumot yo'q (jami bajarilgan: {bajarilgan})")

    if employee.is_rtm_staff:
        completed_by_me = (
            await session.execute(
                select(func.count()).where(
                    Request.assigned_to_employee_id == employee.id,
                    Request.status == RequestStatus.COMPLETED.value,
                )
            )
        ).scalar_one()
        avg_rating = (
            await session.execute(select(func.avg(Rating.score)).where(Rating.rated_employee_id == employee.id))
        ).scalar_one()

        lines.append(f"\n👤 Siz shaxsan bajargan: {completed_by_me} ta")
        lines.append(f"⭐ O'rtacha bahoyingiz: {round(avg_rating, 2) if avg_rating else '-'}")

    await message.answer("\n".join(lines))
