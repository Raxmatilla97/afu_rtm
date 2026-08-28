"""Quick login in the bot: employee id number, then a password set here.

The rules live in ``afu_shared.quick_login`` so the web form behaves identically. What is
in this file is the conversation: which question comes next, what a wrong answer looks
like, and which messages are allowed to survive it.

Two cleanup rules run through the whole flow. A typed password is deleted from the chat
immediately rather than on the usual timer — a secret sitting in a chat history for five
seconds is five seconds too long. And the "we emailed you a reset link" notice is the one
message here that must NOT be swept away: the person has to leave Telegram, open their
mail, set a new password on the web and come back, and the instructions have to still be
there when they do. It is cleared on the next successful login, which is the moment it
stops being true.
"""

import logging
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared import quick_login
from afu_shared.models import Employee
from afu_shared.passwords import mask_email
from app.callbacks import QuickCB
from app.keyboards.common import contact_request_keyboard
from app.screens import auth as auth_screens
from app.screens import menu as menu_screens
from app.states.quick_login import QuickLoginStates
from app.ui.anchor import render
from app.utils.transient import (
    clear_sticky,
    purge_transients,
    remember_sticky,
    send_transient,
)

logger = logging.getLogger(__name__)

router = Router(name="quick_login")

#: Deliberately permissive. This address only has to reach its owner; refusing an unusual
#: but valid one would leave somebody with no way to recover a password at all.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")


def _reset_sent_text(masked: str, full_name: str) -> str:
    return (
        "📧 <b>Parolni tiklash havolasi yuborildi</b>\n\n"
        f"👤 {full_name}\n"
        f"✉️ Manzil: <b>{masked}</b>\n\n"
        "<b>Endi nima qilish kerak:</b>\n"
        "1. Pochtangizni oching (kerak bo'lsa «Spam» papkasini ham tekshiring).\n"
        "2. Xatdagi <b>«Yangi parol o'rnatish»</b> havolasini bosing — rtm.afu.uz sayti "
        "ochiladi.\n"
        "3. Saytda yangi parolni ikki marta yozib saqlang.\n"
        "4. Shu chatga qayting, <b>⚡ Tezkor kirish</b> ni bosing va ID raqamingiz bilan "
        "yangi parolni kiriting.\n\n"
        "<i>Havola 1 soat davomida amal qiladi. Bu xabar siz qaytadan kirganingizdan "
        "so'ng o'chiriladi.</i>"
    )


async def _delete_now(message: Message) -> None:
    """Take a typed secret out of the chat straight away.

    The autoclean middleware would get to it in a few seconds; a password does not get a
    few seconds. Deleting twice is harmless — the later job swallows "already gone".
    """
    try:
        await message.delete()
    except TelegramAPIError as exc:
        logger.debug("Could not delete a secret message in %s: %r", message.chat.id, exc)


async def _employee_from_state(
    state: FSMContext, session: AsyncSession
) -> tuple[Employee | None, str]:
    """The employee this conversation is about, re-read rather than cached."""
    data = await state.get_data()
    employee_id = data.get("quick_employee_id")
    id_number = str(data.get("quick_id_number") or "")
    if not employee_id:
        return None, id_number
    return await session.get(Employee, int(employee_id)), id_number


async def _finish_login(
    *,
    employee: Employee,
    telegram_user_id: int,
    chat_id: int,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    """Link this Telegram account to the employee and show them where they landed."""
    await quick_login.link_telegram(session, employee, telegram_user_id)
    await session.commit()
    await state.clear()

    # The reset instructions have done their job, and the transients from failed attempts
    # are noise now.
    await clear_sticky(bot, redis, chat_id)
    await purge_transients(redis, arq_pool, chat_id)

    if employee.verified_at is None:
        # Still owes us a phone number: the group card shows it to whoever takes the job.
        await render(bot, redis, chat_id, auth_screens.build_contact_screen(), force_new=True)
        await send_transient(
            bot, redis, arq_pool, chat_id,
            "Telefon raqamingizni ulashing:",
            ttl=120,
            reply_markup=contact_request_keyboard(),
        )
        return

    await render(bot, redis, chat_id, menu_screens.build_menu(employee), force_new=True)
    await send_transient(
        bot, redis, arq_pool, chat_id,
        f"✅ Xush kelibsiz, {employee.full_name}!",
        ttl=15,
    )


@router.callback_query(QuickCB.filter(F.act == "start"))
async def start_quick_login(
    callback: CallbackQuery, state: FSMContext, bot: Bot, redis: Redis
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.set_state(QuickLoginStates.awaiting_id_number)
    await render(bot, redis, callback.message.chat.id, auth_screens.build_quick_id_screen())


@router.callback_query(QuickCB.filter(F.act == "back"))
async def back_to_options(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.clear()
    chat_id = callback.message.chat.id
    screen = await auth_screens.build_login_screen(
        session, telegram_user_id=callback.from_user.id, chat_id=chat_id
    )
    await render(bot, redis, chat_id, screen)


@router.message(QuickLoginStates.awaiting_id_number, F.text)
async def received_id_number(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    typed = (message.text or "").strip()
    employee = await quick_login.employee_by_id_number(session, typed)

    if employee is None:
        await send_transient(
            bot, redis, arq_pool, message.chat.id,
            "❌ Bunday xodim ID raqami topilmadi. Raqamni tekshirib, qaytadan yuboring.",
            ttl=20,
        )
        return

    if not employee.is_eligible:
        await state.clear()
        await render(
            bot, redis, message.chat.id,
            auth_screens.build_ineligible_screen(employee),
            force_new=True,
        )
        return

    locked = quick_login.lock_minutes_remaining(employee)
    if locked:
        await send_transient(
            bot, redis, arq_pool, message.chat.id,
            f"🔒 Bu hisob vaqtincha bloklangan. {locked} daqiqadan keyin urinib ko'ring.",
            ttl=30,
        )
        return

    await state.update_data(
        quick_employee_id=employee.id, quick_id_number=employee.employee_id_number
    )
    department = employee.department.name if employee.department else None

    if employee.quick_password_hash:
        await state.set_state(QuickLoginStates.awaiting_password)
        await render(
            bot, redis, message.chat.id,
            auth_screens.build_quick_password_screen(employee.full_name, department),
            force_new=True,
        )
        return

    await state.set_state(QuickLoginStates.awaiting_new_password)
    await render(
        bot, redis, message.chat.id,
        auth_screens.build_quick_setup_screen(employee.full_name, department),
        force_new=True,
    )


@router.message(QuickLoginStates.awaiting_new_password, F.text)
async def received_new_password(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    await _delete_now(message)
    employee, _ = await _employee_from_state(state, session)
    if employee is None:
        await state.set_state(QuickLoginStates.awaiting_id_number)
        await render(bot, redis, message.chat.id, auth_screens.build_quick_id_screen())
        return

    try:
        await quick_login.claim_account(
            session, employee, message.text or "", telegram_user_id=message.from_user.id
        )
    except quick_login.WeakPassword as exc:
        await send_transient(bot, redis, arq_pool, message.chat.id, f"⚠️ {exc}", ttl=25)
        return
    except PermissionError as exc:
        await state.clear()
        await send_transient(bot, redis, arq_pool, message.chat.id, f"🔒 {exc}", ttl=40)
        screen = await auth_screens.build_login_screen(
            session, telegram_user_id=message.from_user.id, chat_id=message.chat.id
        )
        await render(bot, redis, message.chat.id, screen, force_new=True)
        return

    await session.commit()
    await state.set_state(QuickLoginStates.awaiting_email)
    await render(
        bot, redis, message.chat.id,
        auth_screens.build_quick_email_screen(employee.full_name),
        force_new=True,
    )


@router.message(QuickLoginStates.awaiting_email, F.text)
async def received_email(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    email = (message.text or "").strip()
    if not _EMAIL_RE.match(email):
        await send_transient(
            bot, redis, arq_pool, message.chat.id,
            "⚠️ Bu elektron pochta manziliga o'xshamayapti. Masalan: ism@afu.uz",
            ttl=20,
        )
        return

    employee, _ = await _employee_from_state(state, session)
    if employee is None:
        await state.set_state(QuickLoginStates.awaiting_id_number)
        await render(bot, redis, message.chat.id, auth_screens.build_quick_id_screen())
        return

    await quick_login.set_recovery_email(session, employee, email)
    await _finish_login(
        employee=employee,
        telegram_user_id=message.from_user.id,
        chat_id=message.chat.id,
        state=state,
        session=session,
        bot=bot,
        redis=redis,
        arq_pool=arq_pool,
    )


@router.message(QuickLoginStates.awaiting_password, F.text)
async def received_password(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    await _delete_now(message)
    employee, id_number = await _employee_from_state(state, session)
    if employee is None or not id_number:
        await state.set_state(QuickLoginStates.awaiting_id_number)
        await render(bot, redis, message.chat.id, auth_screens.build_quick_id_screen())
        return

    result = await quick_login.check_password(session, id_number, message.text or "")
    department = employee.department.name if employee.department else None

    if result.ok and result.employee is not None:
        await _finish_login(
            employee=result.employee,
            telegram_user_id=message.from_user.id,
            chat_id=message.chat.id,
            state=state,
            session=session,
            bot=bot,
            redis=redis,
            arq_pool=arq_pool,
        )
        return

    await session.commit()

    if result.outcome is quick_login.Outcome.LOCKED:
        note = (
            f"Parol bir necha marta noto'g'ri kiritildi. {result.locked_minutes} daqiqadan "
            "keyin urinib ko'ring yoki parolni tiklang."
        )
    elif result.outcome is quick_login.Outcome.NEEDS_SETUP:
        await state.set_state(QuickLoginStates.awaiting_new_password)
        await render(
            bot, redis, message.chat.id,
            auth_screens.build_quick_setup_screen(employee.full_name, department),
            force_new=True,
        )
        return
    else:
        note = f"Parol noto'g'ri. Yana {result.attempts_left} ta urinish qoldi."

    await render(
        bot, redis, message.chat.id,
        auth_screens.build_quick_password_screen(employee.full_name, department, note=note),
        force_new=True,
    )


@router.callback_query(QuickCB.filter(F.act == "reset"))
async def request_password_reset(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    """Mail a reset link and leave the instructions standing in the chat."""
    if callback.message is None:
        await callback.answer()
        return
    chat_id = callback.message.chat.id

    employee, _ = await _employee_from_state(state, session)
    if employee is None:
        await callback.answer("Avval xodim ID raqamingizni yuboring.", show_alert=True)
        return

    if not employee.recovery_email:
        await callback.answer(
            "Bu hisobga elektron pochta biriktirilmagan, shuning uchun parolni avtomatik "
            "tiklab bo'lmaydi. RTM bilan bog'laning.",
            show_alert=True,
        )
        return

    token = await quick_login.start_password_reset(session, employee)
    await session.commit()
    if token:
        await arq_pool.enqueue_job("send_password_reset_email", employee.id, token)

    await callback.answer("📧 Xat yuborildi")
    sent = await bot.send_message(
        chat_id,
        _reset_sent_text(mask_email(employee.recovery_email), employee.full_name),
        parse_mode="HTML",
    )
    # Sticky, not transient: this has to survive the trip to the mailbox and back.
    await remember_sticky(redis, chat_id, sent.message_id)


# StateFilter over the whole group: aiogram states do not support `|`, and naming the
# group also means a state added later is covered without touching this line.
@router.message(StateFilter(QuickLoginStates))
async def wrong_kind_of_answer(
    message: Message, bot: Bot, redis: Redis, arq_pool: ArqRedis
) -> None:
    """A photo or a sticker where a line of text was expected.

    Without this the message falls through to the auth guard, which redraws the login
    screen and quietly throws away the step the user was on.
    """
    await send_transient(
        bot, redis, arq_pool, message.chat.id,
        "Iltimos, javobni matn ko'rinishida yuboring.",
        ttl=15,
    )
