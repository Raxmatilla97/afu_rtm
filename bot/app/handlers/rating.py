from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Employee, Rating, Request

router = Router(name="rating")


@router.callback_query(F.data.startswith("rate:"))
async def rate_request(callback: CallbackQuery, session: AsyncSession, employee: Employee | None) -> None:
    _, request_id_str, score_str = callback.data.split(":")
    request_id = int(request_id_str)
    score = int(score_str)

    request = await session.get(Request, request_id)
    if not request or not employee or request.requester_employee_id != employee.id:
        await callback.answer("Bu murojaat sizga tegishli emas.", show_alert=True)
        return

    existing = (
        await session.execute(select(Rating).where(Rating.request_id == request_id))
    ).scalar_one_or_none()
    if existing:
        await callback.answer("Siz bu murojaatni allaqachon baholagansiz.", show_alert=True)
        return

    if not request.assigned_to_employee_id:
        await callback.answer("Bu murojaat hech kimga tayinlanmagan.", show_alert=True)
        return

    session.add(
        Rating(
            request_id=request.id,
            rated_employee_id=request.assigned_to_employee_id,
            rated_by_employee_id=employee.id,
            score=score,
        )
    )
    await session.flush()

    await callback.message.edit_text(callback.message.text + f"\n\n⭐ Bahoyingiz: {score}/5. Rahmat!")
    await callback.answer("Rahmat!")
