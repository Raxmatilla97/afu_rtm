from aiogram import F, Router
from aiogram.types import Message
from arq import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Employee, Request
from app.keyboards.common import BTN_MY_REQUESTS
from app.utils.transient import schedule_delete

router = Router(name="own_requests")

STATUS_LABELS = {
    "new": "🆕 Yangi",
    "assigned": "👤 Tayinlangan",
    "in_progress": "⏳ Jarayonda",
    "completed": "✅ Bajarilgan",
    "cancelled": "❌ Bekor qilingan",
}


@router.message(F.text == BTN_MY_REQUESTS)
async def show_own_requests(
    message: Message, session: AsyncSession, employee: Employee | None, arq_pool: ArqRedis
) -> None:
    await schedule_delete(arq_pool, message.chat.id, message.message_id)

    if employee is None or not employee.is_eligible:
        await message.answer("Avval shaxsingizni tasdiqlashingiz kerak. /start ni bosing.")
        return

    requests = list(
        (
            await session.execute(
                select(Request)
                .where(Request.requester_employee_id == employee.id)
                .order_by(Request.created_at.desc())
                .limit(10)
            )
        ).scalars()
    )

    if not requests:
        await message.answer("Sizda hali murojaatlar yo'q.")
        return

    lines = ["📋 Oxirgi murojaatlaringiz:\n"]
    for r in requests:
        status_label = STATUS_LABELS.get(r.status, r.status)
        lines.append(f"{r.display_number} — {r.category.label_uz} — {status_label}")

    await message.answer("\n".join(lines))
