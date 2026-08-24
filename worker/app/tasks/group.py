"""Posting and maintaining request cards in the RTM group chats.

One card per request, edited in place for its whole life, plus a short reply line whenever
something actually happens. The split is deliberate: an edit changes what the card says but
notifies nobody, so a group watching only edits would never learn that a job came in. The
reply line is what buzzes; the card is what is true.
"""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import ReplyParameters
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.assignments import assignees_of
from afu_shared.db import session_scope
from afu_shared.group_card import build_card_keyboard, build_card_text
from afu_shared.media import send_attachments
from afu_shared.models import (
    Employee,
    NotificationChat,
    Rating,
    Request,
    RequestAttachment,
    RequestGroupPost,
)
from app.bot_client import get_bot

logger = logging.getLogger(__name__)


async def _active_chats(session: AsyncSession) -> list[NotificationChat]:
    return list(
        (
            await session.execute(
                select(NotificationChat).where(NotificationChat.is_active.is_(True))
            )
        ).scalars()
    )


async def _card_content(session: AsyncSession, request: Request):
    """Everything the card shows, gathered in one place so post and edit cannot diverge."""
    requester = await session.get(Employee, request.requester_employee_id)
    assignees = await assignees_of(session, request.id)
    attachments = list(
        (
            await session.execute(
                select(RequestAttachment)
                .where(RequestAttachment.request_id == request.id)
                .order_by(RequestAttachment.id)
            )
        ).scalars()
    )
    ratings = list(
        (
            await session.execute(select(Rating).where(Rating.request_id == request.id))
        ).scalars()
    )

    text = build_card_text(request, requester, assignees, attachments, ratings)
    keyboard = build_card_keyboard(request, assignees, attachments)
    return text, keyboard


async def _deactivate(session: AsyncSession, chat_id: int) -> None:
    chat = await session.get(NotificationChat, chat_id)
    if chat is not None and chat.is_active:
        chat.is_active = False
        logger.info("Group %s deactivated: the bot can no longer post there", chat_id)


async def publish_request_card(ctx: dict, request_id: int) -> None:
    """Announce a request in every registered group."""
    bot = get_bot()

    async with session_scope() as session:
        request = await session.get(Request, request_id)
        if request is None:
            logger.error("publish_request_card: request %s not found", request_id)
            return

        chats = await _active_chats(session)
        if not chats:
            return

        already = {
            post.chat_id
            for post in (
                await session.execute(
                    select(RequestGroupPost).where(RequestGroupPost.request_id == request_id)
                )
            ).scalars()
        }

        text, keyboard = await _card_content(session, request)

        for chat in chats:
            if chat.chat_id in already:
                continue
            try:
                sent = await bot.send_message(
                    chat.chat_id, text, parse_mode="HTML", reply_markup=keyboard
                )
            except TelegramForbiddenError:
                await _deactivate(session, chat.chat_id)
                continue
            except (TelegramBadRequest, TelegramRetryAfter) as exc:
                logger.warning("Could not post card for %s to %s: %s", request_id, chat.chat_id, exc)
                continue

            session.add(
                RequestGroupPost(
                    request_id=request_id, chat_id=chat.chat_id, message_id=sent.message_id
                )
            )


async def refresh_request_cards(
    ctx: dict, request_id: int, note: str | None = None
) -> None:
    """Bring every card for this request up to date, and optionally announce what changed.

    ``note`` is one short line ("X took this on") sent as a reply to the card. It exists
    because an edit is silent: without it the group would only ever be notified about brand
    new requests, and everything that happened afterwards would go unseen.
    """
    bot = get_bot()

    async with session_scope() as session:
        request = await session.get(Request, request_id)
        if request is None:
            return

        posts = list(
            (
                await session.execute(
                    select(RequestGroupPost).where(RequestGroupPost.request_id == request_id)
                )
            ).scalars()
        )
        if not posts:
            return

        text, keyboard = await _card_content(session, request)

        for post in posts:
            if not await _edit_card(bot, post, text, keyboard):
                await _deactivate(session, post.chat_id)
                continue
            if note:
                await _reply_note(bot, post, note)


async def _edit_card(bot: Bot, post: RequestGroupPost, text: str, keyboard) -> bool:
    """Returns False only when the chat itself is unusable, not on a harmless edit failure."""
    try:
        await bot.edit_message_text(
            text=text,
            chat_id=post.chat_id,
            message_id=post.message_id,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except TelegramForbiddenError:
        return False
    except TelegramBadRequest as exc:
        # "not modified" means the card already says this — a refresh triggered by something
        # the card does not display. Nothing is wrong.
        if "not modified" not in str(exc).lower():
            logger.warning(
                "Could not edit card %s in %s: %s", post.message_id, post.chat_id, exc
            )
    except TelegramRetryAfter as exc:
        logger.info("Flood limit editing card in %s (retry after %s)", post.chat_id, exc.retry_after)
    return True


async def _reply_note(bot: Bot, post: RequestGroupPost, note: str) -> None:
    try:
        await bot.send_message(
            post.chat_id,
            note,
            parse_mode="HTML",
            reply_parameters=ReplyParameters(
                message_id=post.message_id,
                # The card may have been cleared out of the group by a moderator; the note
                # is still worth delivering on its own.
                allow_sending_without_reply=True,
            ),
        )
    except (TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter) as exc:
        logger.warning("Could not post note to %s: %s", post.chat_id, exc)


#: How long replayed files stay in a group before the bot clears them away.
GROUP_MEDIA_TTL_SECONDS = 10 * 60


async def send_request_files_to_chat(ctx: dict, request_id: int, chat_id: int) -> None:
    """Replay a request's files into a group, on request from its card.

    Group copies are temporary. A shared chat that keeps every photo anyone ever asked to
    see becomes unusable within a week, and the files are never lost: the card's button
    fetches them again, and the web interface keeps them permanently. The countdown is
    written into the caption rather than posted as its own message, so the warning cannot
    itself become the clutter it is there to prevent.
    """
    async with session_scope() as session:
        request = await session.get(Request, request_id)
        if request is None:
            return
        attachments = list(
            (
                await session.execute(
                    select(RequestAttachment)
                    .where(RequestAttachment.request_id == request_id)
                    .order_by(RequestAttachment.id)
                )
            ).scalars()
        )
        display_number = request.display_number

    if not attachments:
        return

    minutes = GROUP_MEDIA_TTL_SECONDS // 60
    sent = await send_attachments(
        get_bot(), chat_id, attachments,
        caption=(
            f"📎 <b>{display_number}</b> — materiallar\n"
            f"<i>🕙 {minutes} daqiqadan so'ng bu fayllar o'chiriladi. "
            "Kerak bo'lsa kartochkadagi tugmani qayta bosing.</i>"
        ),
    )
    for message_id in sent:
        await ctx["redis"].enqueue_job(
            "delete_telegram_message",
            chat_id,
            message_id,
            _defer_by=GROUP_MEDIA_TTL_SECONDS,
        )
