"""Storing one conversation message — text, media, or both.

Every write into a request thread goes through here: the requester replying, staff
answering, an internal note, a completion report. They differ only in ``visibility`` and in
who is allowed to write, so keeping one storage path means media support could not land in
some directions and quietly miss others.
"""

from aiogram import Bot
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import MessageVisibility
from afu_shared.media import persist_media
from afu_shared.models import RequestAttachment, RequestMessage


def message_text(message: Message) -> str | None:
    """The words in a message, wherever Telegram put them.

    A caption on a photo is the same thing to a reader as the text of a plain message, so
    both land in ``body`` and neither has to be looked for in two places later.
    """
    raw = (message.text or message.caption or "").strip()
    return raw or None


async def store_thread_message(
    session: AsyncSession,
    bot: Bot,
    message: Message,
    *,
    request_id: int,
    employee_id: int,
    visibility: MessageVisibility,
) -> tuple[RequestMessage, RequestAttachment | None]:
    """Persist the message and any file it carries, linked together."""
    row = RequestMessage(
        request_id=request_id,
        author_employee_id=employee_id,
        visibility=visibility.value,
        body=message_text(message),
    )
    session.add(row)
    await session.flush()

    attachment = await persist_media(
        session, bot, message,
        request_id=request_id,
        employee_id=employee_id,
        message_row_id=row.id,
    )
    return row, attachment
