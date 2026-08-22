from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import TelegramLinkStatus
from afu_shared.models import Employee, TelegramLinkToken
from app.keyboards.common import main_menu_keyboard, remove_keyboard
from app.states.verification import VerificationStates
from app.utils.transient import send_transient

router = Router(name="contact")


@router.message(VerificationStates.awaiting_contact, F.contact)
async def process_contact(message: Message, state: FSMContext, session: AsyncSession) -> None:
    contact = message.contact

    if contact.user_id != message.from_user.id:
        await message.answer("Iltimos, faqat o'zingizning kontaktingizni yuboring.")
        return

    data = await state.get_data()
    candidate_id = data.get("candidate_employee_id")
    employee = await session.get(Employee, candidate_id) if candidate_id else None

    if not employee or not employee.is_eligible:
        await message.answer("Xatolik yuz berdi. Qaytadan /start bosing.", reply_markup=remove_keyboard())
        await state.clear()
        return

    if employee.telegram_user_id and employee.telegram_user_id != message.from_user.id:
        await message.answer(
            "Bu xodim allaqachon boshqa Telegram hisobiga bog'langan.", reply_markup=remove_keyboard()
        )
        await state.clear()
        return

    other_link = (
        await session.execute(select(Employee).where(Employee.telegram_user_id == message.from_user.id))
    ).scalar_one_or_none()
    if other_link and other_link.id != employee.id:
        await message.answer(
            "Sizning Telegram hisobingiz allaqachon boshqa xodimga bog'langan.",
            reply_markup=remove_keyboard(),
        )
        await state.clear()
        return

    employee.telegram_user_id = message.from_user.id
    employee.telegram_username = message.from_user.username
    employee.phone_number = contact.phone_number
    employee.verified_at = datetime.now(timezone.utc)

    link_token = data.get("link_token")
    if link_token:
        link = await session.get(TelegramLinkToken, link_token)
        if link and link.status == TelegramLinkStatus.PENDING.value:
            link.status = TelegramLinkStatus.COMPLETED.value
            link.completed_at = datetime.now(timezone.utc)

    await state.clear()
    await message.answer(
        f"Rahmat, {employee.full_name}! Siz muvaffaqiyatli tasdiqlandingiz.",
        reply_markup=main_menu_keyboard(is_rtm_staff=employee.is_rtm_staff),
    )


@router.message(VerificationStates.awaiting_contact)
async def reject_non_contact(message: Message, redis: Redis, arq_pool: ArqRedis) -> None:
    await send_transient(
        message.bot,
        redis,
        arq_pool,
        message.chat.id,
        "Iltimos, pastdagi tugma orqali kontaktingizni yuboring.",
    )
