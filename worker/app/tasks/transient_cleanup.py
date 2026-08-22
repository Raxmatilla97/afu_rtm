import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.bot_client import get_bot

logger = logging.getLogger(__name__)


async def delete_telegram_message(ctx: dict, chat_id: int, message_id: int) -> None:
    bot = get_bot()
    try:
        await bot.delete_message(chat_id, message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        # Already deleted, too old, or the chat is gone — deleting twice is harmless.
        logger.debug("Could not delete message %s in chat %s (already gone)", message_id, chat_id)
