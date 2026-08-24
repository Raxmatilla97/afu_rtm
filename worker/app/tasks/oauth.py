"""Tells the bot user that their HEMIS login landed.

The bot is long-polling and has no HTTP surface, so the backend cannot call it directly.
The worker owns a Bot client, so it delivers the follow-up message instead.
"""

import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from redis.asyncio import Redis

from afu_shared.db import session_scope
from afu_shared.labels import BTN_SHARE_CONTACT
from afu_shared.models import Employee
from afu_shared.settings import settings
from app.bot_client import get_bot

logger = logging.getLogger(__name__)

#: Mirrors ``bot/app/ui/anchor.py``. The worker cannot import the bot package, and the key
#: is the whole contract, so it is repeated rather than shared.
ANCHOR_KEY_TMPL = "bot:anchor:{chat_id}"


def _contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SHARE_CONTACT, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def _drop_stale_anchor(chat_id: int) -> None:
    """Remove the bot's login screen once the login has actually happened.

    Otherwise the anchor keeps showing "🔐 HEMIS orqali kirish" above this message, and the
    obvious thing to tap after a confusing login is that button — which starts the whole
    flow over for a user who is already signed in. Dropping the anchor makes the bot mint a
    fresh screen on the next interaction.
    """
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        key = ANCHOR_KEY_TMPL.format(chat_id=chat_id)
        stored = await redis.get(key)
        if stored:
            try:
                await get_bot().delete_message(chat_id, int(stored))
            except (TelegramBadRequest, TelegramForbiddenError):
                logger.debug("Stale anchor %s in chat %s already gone", stored, chat_id)
            await redis.delete(key)
    finally:
        await redis.aclose()


async def notify_oauth_login_complete(
    ctx: dict, employee_id: int, telegram_user_id: int
) -> None:
    async with session_scope() as session:
        employee = await session.get(Employee, employee_id)
        if employee is None:
            logger.error("notify_oauth_login_complete: employee %s not found", employee_id)
            return

        already_onboarded = employee.verified_at is not None
        full_name = employee.full_name

    if not already_onboarded:
        # Private chat: the chat id is the user id. Only mid-onboarding is the anchor
        # necessarily stale — for an already-verified user it is the main menu, which is
        # still perfectly good and should not be thrown away.
        await _drop_stale_anchor(telegram_user_id)

    bot = get_bot()
    if already_onboarded:
        text = f"✅ Xush kelibsiz, {full_name}!\n\n/menu — asosiy menyu"
        markup = None
    else:
        text = (
            f"✅ HEMIS orqali tanildingiz: <b>{full_name}</b>\n\n"
            "Oxirgi qadam: pastdagi tugma orqali telefon raqamingizni ulashing."
        )
        markup = _contact_keyboard()

    try:
        await bot.send_message(telegram_user_id, text, parse_mode="HTML", reply_markup=markup)
    except TelegramForbiddenError:
        logger.warning("Cannot notify user %s after OAuth: bot blocked", telegram_user_id)
