import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import delete as sql_delete

from afu_shared.db import session_scope
from afu_shared.models import GroupMessage
from app.bot_client import get_bot

logger = logging.getLogger(__name__)


async def delete_telegram_message(ctx: dict, chat_id: int, message_id: int) -> None:
    bot = get_bot()
    try:
        await bot.delete_message(chat_id, message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        # Already deleted, too old, or the chat is gone — deleting twice is harmless.
        logger.debug("Could not delete message %s in chat %s (already gone)", message_id, chat_id)

    # Whether or not Telegram obliged, this message is not something the admin panel should
    # keep offering to delete. Most calls here are for a private-chat message that was never
    # logged, and the statement then matches nothing.
    async with session_scope() as session:
        await session.execute(
            sql_delete(GroupMessage).where(
                GroupMessage.chat_id == chat_id, GroupMessage.message_id == message_id
            )
        )
