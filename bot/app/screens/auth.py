"""Onboarding screens: HEMIS login, then the contact share."""

from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.common import contact_request_keyboard, hemis_login_keyboard
from app.middlewares.identity import AuthState
from app.services.oauth_link import create_login_url
from app.ui.anchor import Screen, render
from app.utils.transient import send_transient

WELCOME = (
    "👋 <b>RTM Murojaatlar tizimi</b>\n"
    "Alfraganus University — Raqamli texnologiyalar markazi\n\n"
    "Bu bot orqali RTM ga murojaat yuborasiz va uning holatini kuzatib borasiz.\n\n"
    "Boshlash uchun HEMIS hisobingiz bilan kiring. Havola brauzerda ochiladi — "
    "kirish tugagach botga qaytasiz."
)

CONTACT_PROMPT = (
    "✅ HEMIS orqali tanildingiz.\n\n"
    "Endi oxirgi qadam: pastdagi tugma orqali telefon raqamingizni ulashing. "
    "Bu raqam sizga xabar yuborish uchun kerak bo'ladi."
)

INELIGIBLE = (
    "⛔️ <b>Ruxsat cheklangan</b>\n\n"
    "Hisobingiz hozirda faol emas. Agar bu xato deb hisoblasangiz, "
    "RTM bilan bog'laning."
)


async def build_login_screen(session: AsyncSession, *, telegram_user_id: int, chat_id: int) -> Screen:
    # A fresh state is minted per render, so the button is never stale for long.
    url = await create_login_url(session, telegram_user_id=telegram_user_id, chat_id=chat_id)
    return Screen(text=WELCOME, keyboard=hemis_login_keyboard(url))


def build_contact_screen() -> Screen:
    return Screen(text=CONTACT_PROMPT, keyboard=None)


def build_ineligible_screen() -> Screen:
    return Screen(text=INELIGIBLE, keyboard=None)


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
        await render(bot, redis, chat_id, build_ineligible_screen(), force_new=force_new)
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
