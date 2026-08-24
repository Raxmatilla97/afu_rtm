"""Statistics screen."""

from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import RequestStatus
from afu_shared.models import Employee, Rating, Request
from app.keyboards.common import menu_button
from app.ui.anchor import Screen

MONTHS_SHOWN = 6


async def build_stats(session: AsyncSession, employee: Employee) -> Screen:
    month = func.date_trunc("month", Request.completed_at).label("month")
    rows = list(
        (
            await session.execute(
                select(month, func.count().label("total"))
                .where(Request.status == RequestStatus.COMPLETED.value)
                .group_by(month)
                .order_by(month.desc())
                .limit(MONTHS_SHOWN)
            )
        ).all()
    )

    total_completed = (
        await session.execute(
            select(func.count())
            .select_from(Request)
            .where(Request.status == RequestStatus.COMPLETED.value)
        )
    ).scalar_one()

    lines = ["📊 <b>Statistika</b>\n"]
    if rows:
        lines.append("<b>Oylar kesimida bajarilgan:</b>")
        for month_value, count in rows:
            lines.append(f"• {month_value:%Y-%m}: {count} ta")
    lines.append(f"\nJami bajarilgan: <b>{total_completed}</b> ta")

    my_total = (
        await session.execute(
            select(func.count())
            .select_from(Request)
            .where(Request.requester_employee_id == employee.id)
        )
    ).scalar_one()
    lines.append(f"Sizning murojaatlaringiz: <b>{my_total}</b> ta")

    if employee.is_rtm_staff:
        done_by_me = (
            await session.execute(
                select(func.count())
                .select_from(Request)
                .where(
                    Request.assigned_to_employee_id == employee.id,
                    Request.status == RequestStatus.COMPLETED.value,
                )
            )
        ).scalar_one()
        avg_score = (
            await session.execute(
                select(func.avg(Rating.score)).where(Rating.rated_employee_id == employee.id)
            )
        ).scalar_one()

        lines.append("\n<b>Sizning ishingiz</b>")
        lines.append(f"• Bajargan: {done_by_me} ta")
        lines.append(
            f"• O'rtacha baho: {round(float(avg_score), 2)} / 5" if avg_score else "• Baho: —"
        )

    return Screen(
        text="\n".join(lines),
        keyboard=InlineKeyboardMarkup(inline_keyboard=[[menu_button()]]),
    )
