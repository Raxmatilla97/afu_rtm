"""Onboarding screens: the two ways in, then the contact share.

Quick login comes first on the screen and in this file, because it is the one that works.
HEMIS moved its sign-in behind One-ID, which most staff have not linked and cannot remember
a password for, so the OAuth button — the only door until now — was turning people away at
the step before they had even reached this bot.
"""

from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.common import (
    contact_request_keyboard,
    hemis_login_keyboard,
    login_options_keyboard,
    quick_back_keyboard,
    quick_password_keyboard,
)
from app.middlewares.identity import AuthState
from app.services.oauth_link import create_login_url
from app.ui.anchor import Screen, render
from app.utils.transient import send_transient

WELCOME = (
    "👋 <b>RTM Murojaatlar tizimi</b>\n"
    "Alfraganus University — Raqamli texnologiyalar markazi\n\n"
    "Bu bot orqali RTM ga murojaat yuborasiz va uning holatini kuzatib borasiz.\n\n"
    "<b>Kirishning ikki yo'li bor:</b>\n"
    "⚡ <b>Tezkor kirish</b> — xodim ID raqamingiz va shu bot uchun o'zingiz o'ylab "
    "topadigan parol. Eng oson yo'l.\n"
    "🔐 <b>HEMIS orqali</b> — HEMIS hisobingiz bilan. HEMIS hozir One-ID orqali "
    "kirishni so'raydi, shuning uchun bu yo'l ancha qiyinroq."
)

QUICK_ASK_ID = (
    "⚡ <b>Tezkor kirish</b>\n\n"
    "<b>Xodim ID raqamingizni</b> yuboring.\n\n"
    "<i>Bu raqam xodimlik guvohnomangizda va HEMIS profilingizda yozilgan — "
    "masalan, 4572612075.</i>"
)

CONTACT_PROMPT = (
    "✅ Tanildingiz.\n\n"
    "Endi oxirgi qadam: pastdagi tugma orqali telefon raqamingizni ulashing. "
    "Bu raqam sizga xabar yuborish uchun kerak bo'ladi."
)

INELIGIBLE = (
    "⛔️ <b>Ruxsat cheklangan</b>\n\n"
    "Hisobingiz hozirda faol emas. Agar bu xato deb hisoblasangiz, "
    "RTM bilan bog'laning."
)

#: Separate from INELIGIBLE on purpose. "Your account is not active" reads like a HEMIS
#: problem the person could go and fix; a deliberate block is a decision somebody made, and
#: saying so plainly is what sends them to the right place instead of to the HR office.
BLOCKED = (
    "🚫 <b>Siz botdan foydalana olmaysiz!</b>\n\n"
    "Sizning hisobingiz administrator tomonidan bloklangan.\n\n"
    "Savollaringiz bo'lsa, RTM ma'muriyatiga murojaat qiling."
)


async def build_login_screen(session: AsyncSession, *, telegram_user_id: int, chat_id: int) -> Screen:
    # A fresh OAuth state is minted per render, so the HEMIS button is never stale for long.
    url = await create_login_url(session, telegram_user_id=telegram_user_id, chat_id=chat_id)
    return Screen(text=WELCOME, keyboard=login_options_keyboard(url))


def build_quick_id_screen() -> Screen:
    return Screen(text=QUICK_ASK_ID, keyboard=quick_back_keyboard())


def _where(department: str | None) -> str:
    return f"\n🏢 {department}" if department else ""


def build_quick_setup_screen(full_name: str, department: str | None) -> Screen:
    """Identity first, password second.

    The name goes on the screen before anything is typed. People have been ending up inside
    a colleague's account, and this is the moment to catch a wrong id number — while going
    back still costs one tap and nothing has been claimed.
    """
    return Screen(
        text=(
            "⚡ <b>Tezkor kirish — birinchi marta</b>\n\n"
            f"👤 <b>{full_name}</b>{_where(department)}\n\n"
            "Agar bu siz bo'lmasangiz — «⬅️ Orqaga» ni bosing va ID raqamni tekshiring.\n\n"
            "Siz bo'lsangiz, shu bot uchun <b>parol</b> o'ylab toping va yuboring:\n"
            "• kamida 6 ta belgi\n"
            "• kamida bitta harf va bitta raqam\n"
            "• ID raqamingizning o'zi bo'lmasin\n\n"
            "<i>Yuborilgan parol chatdan darhol o'chiriladi.</i>"
        ),
        keyboard=quick_back_keyboard(),
    )


def build_quick_email_screen(full_name: str) -> Screen:
    return Screen(
        text=(
            "✅ Parol saqlandi.\n\n"
            f"👤 <b>{full_name}</b>\n\n"
            "Endi <b>elektron pochta manzilingizni</b> yuboring. U bitta narsa uchun kerak: "
            "parolni unutsangiz, tiklash havolasi shu manzilga yuboriladi.\n\n"
            "<i>Masalan: ism.familiya@afu.uz</i>"
        ),
        keyboard=None,
    )


def build_quick_password_screen(
    full_name: str, department: str | None, *, note: str | None = None
) -> Screen:
    """Ask a returning user for their password. ``note`` carries a failed attempt.

    The reset button appears only after a password has actually failed — offered up front
    it invites people to reset a password they were about to remember.
    """
    warning = f"\n\n⚠️ {note}" if note else ""
    return Screen(
        text=(
            "⚡ <b>Tezkor kirish</b>\n\n"
            f"👤 <b>{full_name}</b>{_where(department)}\n\n"
            f"Shu bot uchun o'rnatgan <b>parolingizni</b> yuboring.{warning}"
        ),
        keyboard=quick_password_keyboard(offer_reset=note is not None),
    )


def build_contact_screen() -> Screen:
    return Screen(text=CONTACT_PROMPT, keyboard=None)


def build_ineligible_screen(employee=None) -> Screen:
    """Why this person cannot get in — the blocked wording when that is the actual reason."""
    blocked = employee is not None and getattr(employee, "is_blocked", False)
    return Screen(text=BLOCKED if blocked else INELIGIBLE, keyboard=None)


async def show_auth_screen(
    *, chat_id: int, data: dict[str, Any], force_new: bool = False
) -> None:
    """Render whichever onboarding step the user is actually on.

    Called from the auth guard, so it must handle every non-READY state.

    ``force_new`` matters more here than anywhere else: onboarding is exactly when other
    messages pile up below the anchor (the worker's post-OAuth greeting, the contact-share
    prompt, the user's own typing). Editing the anchor in place then updates a screen that
    has scrolled out of view, so the bot looks like it simply ignored the user.
    """
    bot: Bot = data["bot"]
    redis: Redis = data["redis"]
    arq_pool: ArqRedis = data["arq_pool"]
    session: AsyncSession = data["session"]
    auth_state: AuthState = data["auth_state"]
    employee = data.get("employee")

    if auth_state is AuthState.INELIGIBLE:
        await render(
            bot, redis, chat_id, build_ineligible_screen(employee), force_new=force_new
        )
        return

    if auth_state is AuthState.OAUTH_ONLY:
        await render(bot, redis, chat_id, build_contact_screen(), force_new=force_new)
        # The contact button lives on a reply keyboard, which cannot be attached to the
        # anchor — send it as a transient alongside.
        await send_transient(
            bot, redis, arq_pool, chat_id,
            "Telefon raqamingizni ulashing:",
            ttl=120,
            reply_markup=contact_request_keyboard(),
        )
        return

    user_id = employee.telegram_user_id if employee else None
    if user_id is None:
        user_id = chat_id  # private chat: chat id equals the user id
    screen = await build_login_screen(session, telegram_user_id=user_id, chat_id=chat_id)
    await render(bot, redis, chat_id, screen, force_new=force_new)


def login_keyboard_for(url: str) -> InlineKeyboardMarkup:
    return hemis_login_keyboard(url)
