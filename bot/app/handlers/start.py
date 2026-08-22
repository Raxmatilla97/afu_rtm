from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import TelegramLinkStatus
from afu_shared.models import Employee, TelegramLinkToken
from app.keyboards.common import contact_request_keyboard, identity_confirm_keyboard, main_menu_keyboard
from app.states.verification import VerificationStates
from app.utils.rate_limit import register_employee_id_attempt
from app.utils.transient import send_transient

router = Router(name="start")


async def _prompt_identity_confirm(message: Message, state: FSMContext, candidate: Employee) -> None:
    dept = candidate.department.name if candidate.department else "-"
    await state.update_data(candidate_employee_id=candidate.id)
    await state.set_state(VerificationStates.awaiting_identity_confirm)
    await message.answer(
        f"Siz <b>{candidate.full_name}</b> ({dept}) sifatida tasdiqlanmoqchimisiz?",
        reply_markup=identity_confirm_keyboard(),
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee | None,
) -> None:
    await state.clear()

    if employee is not None and employee.is_eligible:
        await message.answer(
            f"Salom, {employee.full_name}! Nima qilmoqchisiz?",
            reply_markup=main_menu_keyboard(is_rtm_staff=employee.is_rtm_staff),
        )
        return

    deep_link_token = command.args
    if deep_link_token:
        link = await session.get(TelegramLinkToken, deep_link_token)
        if link and link.status == TelegramLinkStatus.PENDING.value:
            candidate = await session.get(Employee, link.employee_id)
            if candidate and candidate.is_eligible:
                await state.update_data(link_token=deep_link_token)
                await _prompt_identity_confirm(message, state, candidate)
                return
        await message.answer("Havola eskirgan yoki noto'g'ri. Iltimos, xodim ID raqamingizni yuboring.")

    await state.set_state(VerificationStates.awaiting_employee_id)
    await message.answer(
        "Assalomu alaykum! RTM (Raqamliy texnologiyalar markazi) murojaatlar botiga xush kelibsiz.\n\n"
        "Davom etish uchun HEMIS tizimidagi xodim ID raqamingizni yuboring:"
    )


@router.message(VerificationStates.awaiting_employee_id, F.text)
async def process_employee_id(
    message: Message, state: FSMContext, session: AsyncSession, redis: Redis, arq_pool: ArqRedis
) -> None:
    allowed = await register_employee_id_attempt(redis, message.from_user.id)
    if not allowed:
        await send_transient(
            message.bot,
            redis,
            arq_pool,
            message.chat.id,
            "Urinishlar soni chegarasiga yetdingiz. Iltimos, 10 daqiqadan so'ng qayta urinib ko'ring.",
        )
        return

    employee_id_number = message.text.strip()
    candidate = (
        await session.execute(select(Employee).where(Employee.employee_id_number == employee_id_number))
    ).scalar_one_or_none()

    if not candidate or not candidate.is_eligible:
        await send_transient(
            message.bot,
            redis,
            arq_pool,
            message.chat.id,
            "Bunday ID raqamli faol xodim topilmadi. Qaytadan urinib ko'ring yoki RTM bilan bog'laning.",
        )
        return

    if candidate.telegram_user_id and candidate.telegram_user_id != message.from_user.id:
        await send_transient(
            message.bot,
            redis,
            arq_pool,
            message.chat.id,
            "Bu xodim allaqachon boshqa Telegram hisobiga bog'langan. RTM bilan bog'laning.",
        )
        return

    await _prompt_identity_confirm(message, state, candidate)


@router.callback_query(VerificationStates.awaiting_identity_confirm, F.data == "identity_confirm_no")
async def confirm_identity_no(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(VerificationStates.awaiting_employee_id)
    await callback.message.edit_text("Yaxshi, xodim ID raqamingizni qaytadan yuboring:")
    await callback.answer()


@router.callback_query(VerificationStates.awaiting_identity_confirm, F.data == "identity_confirm_yes")
async def confirm_identity_yes(callback: CallbackQuery, state: FSMContext, redis: Redis, arq_pool: ArqRedis) -> None:
    await state.set_state(VerificationStates.awaiting_contact)
    await callback.message.edit_text("Rahmat! Endi ekran ostidagi tugma orqali telefon raqamingizni ulashing.")
    await send_transient(
        callback.bot,
        redis,
        arq_pool,
        callback.message.chat.id,
        "Kontaktni ulashish uchun pastdagi tugmani bosing:",
        reply_markup=contact_request_keyboard(),
    )
    await callback.answer()
