"""Contact share — the final onboarding step after HEMIS OAuth.

OAuth establishes *who* the person is; this step captures a phone number that Telegram
itself vouches for, which is what ``verified_at`` records.
"""

import logging
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Employee
from app.keyboards.common import remove_keyboard
from app.screens import menu
from app.ui.anchor import render
from app.utils.transient import purge_transients, send_transient

logger = logging.getLogger(__name__)

router = Router(name="contact")


@router.message(F.contact)
async def process_contact(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee | None,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    contact = message.contact
    assert contact is not None

    # A contact card can be forwarded from anyone; only the sender's own counts.
    if contact.user_id != message.from_user.id:
        await send_transient(
            bot, redis, arq_pool, message.chat.id,
            "Iltimos, faqat o'zingizning kontaktingizni yuboring.",
        )
        return

    if employee is None:
        await send_transient(
            bot, redis, arq_pool, message.chat.id,
            "Avval HEMIS orqali kiring. /start ni bosing.",
            reply_markup=remove_keyboard(),
        )
        return

    # Defence in depth: the OAuth callback already enforced these, but a race or a manual
    # database edit should not be able to cross-link two accounts.
    existing = (
        await session.execute(
            select(Employee).where(Employee.telegram_user_id == message.from_user.id)
        )
    ).scalar_one_or_none()
    if existing is not None and existing.id != employee.id:
        await send_transient(
            bot, redis, arq_pool, message.chat.id,
            "Telegram hisobingiz boshqa xodimga bog'langan. RTM bilan bog'laning.",
            reply_markup=remove_keyboard(),
        )
        return

    employee.telegram_user_id = message.from_user.id
    employee.telegram_username = message.from_user.username
    employee.phone_number = contact.phone_number
    employee.verified_at = datetime.now(timezone.utc)
    await session.flush()

    await state.clear()
    await purge_transients(redis, arq_pool, message.chat.id)

    # Drop the reply keyboard: from here on everything is inline on the anchor.
    await send_transient(
        bot, redis, arq_pool, message.chat.id,
        f"✅ Rahmat, {employee.full_name}! Ro'yxatdan o'tish yakunlandi.",
        reply_markup=remove_keyboard(),
    )
    await render(bot, redis, message.chat.id, menu.build_menu(employee), force_new=True)
