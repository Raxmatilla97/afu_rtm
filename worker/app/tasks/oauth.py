"""Tells the bot user that their HEMIS login landed.

The bot is long-polling and has no HTTP surface, so the backend cannot call it directly.
The worker owns a Bot client, so it delivers the follow-up message instead.
"""

import logging

from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from afu_shared.db import session_scope
from afu_shared.labels import BTN_SHARE_CONTACT
from afu_shared.models import Employee
from app.anchor import claim_anchor, drop_anchor
from app.bot_client import get_bot

logger = logging.getLogger(__name__)


def _contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SHARE_CONTACT, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


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

    bot = get_bot()

    if already_onboarded:
        # The anchor is the main menu and is still perfectly good — leave it alone.
        try:
            await bot.send_message(
                telegram_user_id,
                f"✅ Xush kelibsiz, {full_name}!\n\n/menu — asosiy menyu",
                parse_mode="HTML",
            )
        except TelegramForbiddenError:
            logger.warning("Cannot notify user %s after OAuth: bot blocked", telegram_user_id)
        return

    # Private chat: the chat id is the user id. Mid-onboarding the anchor still shows the
    # HEMIS login button, which is exactly the wrong thing to tap next.
    await drop_anchor(bot, telegram_user_id)

    try:
        sent = await bot.send_message(
            telegram_user_id,
            f"✅ HEMIS orqali tanildingiz: <b>{full_name}</b>\n\n"
            "Oxirgi qadam: pastdagi tugma orqali telefon raqamingizni ulashing.",
            parse_mode="HTML",
            reply_markup=_contact_keyboard(),
        )
    except TelegramForbiddenError:
        logger.warning("Cannot notify user %s after OAuth: bot blocked", telegram_user_id)
        return

    # This prompt IS the current screen, so hand it to the bot as the anchor. The moment
    # the contact arrives the bot re-renders with force_new, which deletes it — previously
    # it was an ordinary message and stayed in the chat long after it stopped applying.
    await claim_anchor(telegram_user_id, sent.message_id)
