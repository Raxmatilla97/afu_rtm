"""The anchor message: one message per chat that every screen edits in place.

Navigating by editing a single message is what keeps the chat clean — menus, lists and
detail views never accumulate. Only genuinely durable output (a ticket confirmation, a
completion notice, an incoming message from the other party) is sent as its own message.
"""

import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

ANCHOR_KEY_TMPL = "bot:anchor:{chat_id}"
ANCHOR_TTL_SECONDS = 30 * 24 * 3600


@dataclass(frozen=True)
class Screen:
    text: str
    keyboard: InlineKeyboardMarkup | None = None


def _key(chat_id: int) -> str:
    return ANCHOR_KEY_TMPL.format(chat_id=chat_id)


async def render(
    bot: Bot, redis: Redis, chat_id: int, screen: Screen, *, force_new: bool = False
) -> int | None:
    """Show ``screen`` on the chat's anchor message, creating or replacing it as needed.

    ``force_new`` re-anchors at the bottom of the chat, which matters after a separate
    message has been sent above it. The previous anchor is deleted rather than left
    behind: two live screens in one chat means the user can tap a button on the stale one
    (an expired HEMIS login link, most painfully) and see nothing happen.
    """
    stored = await redis.get(_key(chat_id))

    if force_new and stored:
        await _delete_quietly(bot, chat_id, int(stored))
        await redis.delete(_key(chat_id))
        stored = None

    if stored:
        try:
            await bot.edit_message_text(
                text=screen.text,
                chat_id=chat_id,
                message_id=int(stored),
                reply_markup=screen.keyboard,
            )
            return int(stored)
        except TelegramBadRequest as exc:
            message = str(exc).lower()
            if "message is not modified" in message:
                # Re-rendering an identical screen (e.g. a double tap) is a no-op, not a failure.
                return int(stored)
            if not any(
                hint in message
                for hint in ("message to edit not found", "message can't be edited", "message_id")
            ):
                logger.warning("Unexpected anchor edit failure for chat %s: %s", chat_id, exc)
            # Anchor is gone or uneditable — fall through and send a fresh one.
        except TelegramForbiddenError:
            logger.info("Cannot edit anchor for chat %s: bot blocked", chat_id)
            return None

    try:
        sent = await bot.send_message(chat_id, screen.text, reply_markup=screen.keyboard)
    except TelegramForbiddenError:
        logger.info("Cannot send anchor to chat %s: bot blocked", chat_id)
        return None

    await redis.set(_key(chat_id), sent.message_id, ex=ANCHOR_TTL_SECONDS)
    return sent.message_id


async def _delete_quietly(bot: Bot, chat_id: int, message_id: int) -> None:
    """Best-effort delete. Already gone, older than 48h, or blocked — all fine to ignore."""
    try:
        await bot.delete_message(chat_id, message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.debug("Could not delete old anchor %s in chat %s", message_id, chat_id)


async def forget_anchor(redis: Redis, chat_id: int) -> None:
    await redis.delete(_key(chat_id))
