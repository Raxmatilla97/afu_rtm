"""Outbound Telegram notifications.

The bot long-polls and has no HTTP surface, so everything the backend or another user
triggers is delivered from here. Every notification that concerns a message or a request
also replays that request's files, because a fault report reduced to its text loses most of
what makes it actionable — "the screen looks like this" is a photo, not a sentence.
"""

import logging

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from sqlalchemy import select

from afu_shared.assignments import assignees_of
from afu_shared.callbacks import AsgCB, ReqCB
from afu_shared.db import session_scope
from afu_shared.enums import MessageVisibility
from afu_shared.labels import status_label
from afu_shared.media import describe_attachments, send_attachments
from afu_shared.models import (
    Employee,
    Request,
    RequestAttachment,
    RequestMessage,
)
from app.bot_client import get_bot

logger = logging.getLogger(__name__)


def _rating_keyboard(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐" * score,
                    callback_data=ReqCB(act="rate_set", rid=request_id, score=score).pack(),
                )
                for score in (1, 2, 3)
            ],
            [
                InlineKeyboardButton(
                    text="⭐" * score,
                    callback_data=ReqCB(act="rate_set", rid=request_id, score=score).pack(),
                )
                for score in (4, 5)
            ],
        ]
    )


def _fmt_dt(value) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else "—"


async def _message_attachments(session, message_id: int) -> list[RequestAttachment]:
    """Just the files on one message.

    Relaying a single reply must not re-send the whole history: the recipient wants the
    photo that was just posted, not the four from last week.
    """
    return list(
        (
            await session.execute(
                select(RequestAttachment)
                .where(RequestAttachment.message_id == message_id)
                .order_by(RequestAttachment.id)
            )
        ).scalars()
    )


async def _request_attachments(
    session, request_id: int, *, include_internal: bool
) -> list[RequestAttachment]:
    """Every file on a request.

    ``include_internal`` is not optional on purpose. Files hanging off an internal RTM note
    must never reach the requester, and a default would make it possible to leak them by
    forgetting to think about the audience.
    """
    stmt = (
        select(RequestAttachment)
        .where(RequestAttachment.request_id == request_id)
        .order_by(RequestAttachment.id)
    )
    if not include_internal:
        stmt = stmt.outerjoin(
            RequestMessage, RequestAttachment.message_id == RequestMessage.id
        ).where(
            (RequestAttachment.message_id.is_(None))
            | (RequestMessage.visibility == MessageVisibility.TO_REQUESTER.value)
        )
    return list((await session.execute(stmt)).scalars())


async def _deliver(
    chat_id: int,
    text: str,
    attachments: list[RequestAttachment],
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Send the wording, then the files under it.

    Text first and files second, deliberately: the reader needs to know which request they
    are looking at before three photos and a voice note arrive.
    """
    bot = get_bot()
    try:
        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)
    except TelegramForbiddenError:
        logger.warning("Cannot deliver notification to %s: bot blocked", chat_id)
        return
    except TelegramRetryAfter as exc:
        # Swallowed rather than raised: arq would retry the whole job and re-send every
        # file that already arrived.
        logger.warning("Flood limit delivering to %s (retry after %s)", chat_id, exc.retry_after)
        return

    if attachments:
        await send_attachments(bot, chat_id, attachments)


async def notify_request_assigned(
    ctx: dict, request_id: int, employee_id: int | None = None
) -> None:
    """Tell an RTM staffer that a request is now theirs, with everything they need.

    This is the moment the job actually reaches a person, so it carries the full brief —
    who reported it, how to reach them, the deadline, the description — followed by every
    file the requester sent, each replayed as its original kind so a voice note is still
    playable and a round video is still round.

    ``employee_id`` names who to brief. The group flow passes the person who just pressed
    "I'll take it", who is not necessarily the primary assignee — somebody joining a job a
    colleague already picked up needs the same brief, not a shorter one.
    """
    async with session_scope() as session:
        request = await session.get(Request, request_id)
        if request is None:
            logger.error("notify_request_assigned: request %s not found", request_id)
            return

        target_id = employee_id or request.assigned_to_employee_id
        if target_id is None:
            return

        assignee = await session.get(Employee, target_id)
        if assignee is None or assignee.telegram_user_id is None:
            logger.info(
                "Request %s assigned to employee %s, who has no Telegram link",
                request_id, target_id,
            )
            return

        colleagues = [
            row.employee.full_name
            for row in await assignees_of(session, request_id)
            if row.employee_id != target_id and row.employee
        ]
        requester = await session.get(Employee, request.requester_employee_id)
        # RTM staff, so internal material is theirs to see.
        attachments = await _request_attachments(session, request_id, include_internal=True)

        lines = [
            "🛠 <b>Sizga yangi topshiriq</b>",
            "",
            f"<b>{request.display_number}</b> · {status_label(request.status)}",
            f"Kategoriya: {request.category.label_uz if request.category else '—'}",
        ]
        if requester:
            lines.append(f"\n👤 <b>Murojaatchi:</b> {requester.full_name}")
            if requester.department:
                lines.append(f"Bo'lim: {requester.department.name}")
            if requester.phone_number:
                lines.append(f"Telefon: {requester.phone_number}")
            if requester.telegram_username:
                lines.append(f"Telegram: @{requester.telegram_username}")
        if colleagues:
            lines.append(f"\n🤝 <b>Hamkorlar:</b> {', '.join(colleagues)}")
        lines.append(f"\n⏰ Muddat: {_fmt_dt(request.deadline_at)}")
        lines.append(f"\n<b>Tavsif:</b>\n{request.description}")
        if attachments:
            lines.append(f"\n📎 <b>Materiallar:</b> {describe_attachments(attachments)}")
            lines.append("<i>Fayllar shu xabardan keyin yuboriladi.</i>")

        text = "\n".join(lines)
        chat_id = assignee.telegram_user_id
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🛠 Topshiriqni ochish",
                        callback_data=AsgCB(act="open", rid=request_id).pack(),
                    )
                ]
            ]
        )

    await _deliver(chat_id, text, attachments, reply_markup=keyboard)


async def send_completion_notification(
    ctx: dict, request_id: int, message_id: int | None = None
) -> None:
    """Tell the requester their request is done, and ask them to rate it.

    ``message_id`` points at the completion report when the staffer left one through the
    bot; its media (a photo of the repaired socket, a spoken explanation) is what gets
    replayed here.
    """
    async with session_scope() as session:
        request = await session.get(Request, request_id)
        if request is None:
            logger.error("send_completion_notification: request %s not found", request_id)
            return

        requester = await session.get(Employee, request.requester_employee_id)
        staff = (
            await session.get(Employee, request.assigned_to_employee_id)
            if request.assigned_to_employee_id
            else None
        )
        if not requester or not requester.telegram_user_id:
            return

        # Only the report's own media. Completing from the web leaves no report message, and
        # falling back to "every file on the request" there would post internal RTM material
        # straight to the requester.
        attachments = (
            await _message_attachments(session, message_id) if message_id is not None else []
        )

        text = (
            f"✅ <b>Murojaatingiz bajarildi!</b>\n\n"
            f"№ <b>{request.display_number}</b>\n"
            f"Tavsif: {request.description}\n"
            f"Bajardi: {staff.full_name if staff else 'RTM xodimi'}\n"
            f"Izoh: {request.completion_note or '-'}\n\n"
            f"Xizmat sifatini baholang:"
        )
        chat_id = requester.telegram_user_id

    await _deliver(chat_id, text, attachments, reply_markup=_rating_keyboard(request_id))


async def notify_request_message(
    ctx: dict, request_id: int, author_employee_id: int | None, message_id: int | None = None
) -> None:
    """Deliver one message on a request to whoever should see it.

    Both directions route through here so requester->staff and staff->requester share one
    notification path rather than drifting apart.

    ``author_employee_id`` is None when an admin wrote from the web. An admin has no
    employee row, so they can never be the requester — which makes their message
    RTM-to-requester, exactly like a staffer's.
    """
    async with session_scope() as session:
        request = await session.get(Request, request_id)
        if request is None:
            logger.error("notify_request_message: request %s not found", request_id)
            return

        if message_id is not None:
            message = await session.get(RequestMessage, message_id)
        else:
            # Older enqueued jobs carry no id; the newest message is what they meant.
            message = (
                await session.execute(
                    select(RequestMessage)
                    .where(RequestMessage.request_id == request_id)
                    .order_by(RequestMessage.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if message is None:
            return

        author = (
            await session.get(Employee, author_employee_id) if author_employee_id else None
        )
        author_name = author.full_name if author else "RTM administratori"
        display_number = request.display_number
        internal = message.visibility == MessageVisibility.INTERNAL.value

        attachments = await _message_attachments(session, message.id)
        body = message.body or (
            describe_attachments(attachments) if attachments else "—"
        )

        # A button is attached only when every recipient is certain to pass the screen's
        # ownership check. Both detail screens refuse a request that is not the viewer's,
        # so a button offered to the wrong audience does not merely look odd — it answers
        # "Topshiriq topilmadi" and reads as a broken bot.
        keyboard: InlineKeyboardMarkup | None = None

        if internal:
            # Internal notes go to the other RTM staff, never to the requester. They are
            # not the assignee, so there is nothing for them to open here.
            staff_filter = [
                Employee.is_rtm_staff.is_(True),
                Employee.telegram_user_id.isnot(None),
            ]
            if author_employee_id:
                # Guarded: `Employee.id != None` is NULL in SQL, which would match nobody
                # and silently deliver the note to no one at all.
                staff_filter.append(Employee.id != author_employee_id)
            recipients = list(
                (await session.execute(select(Employee).where(*staff_filter))).scalars()
            )
            text = f"🗂 <b>[Ichki] {display_number}</b> — {author_name}:\n\n{body}"
        elif author_employee_id == request.requester_employee_id:
            # Requester wrote: tell the assignee, or all staff if nobody is assigned yet.
            if request.assigned_to_employee_id:
                assignee = await session.get(Employee, request.assigned_to_employee_id)
                recipients = [assignee] if assignee and assignee.telegram_user_id else []
                keyboard = _keyboard_for(
                    "🛠 Topshiriqni ochish", AsgCB(act="open", rid=request.id).pack()
                )
            else:
                recipients = list(
                    (
                        await session.execute(
                            select(Employee).where(
                                Employee.is_rtm_staff.is_(True),
                                Employee.telegram_user_id.isnot(None),
                            )
                        )
                    ).scalars()
                )
            text = f"💬 <b>{display_number}</b> — murojaatchi {author_name}:\n\n{body}"
        else:
            requester = await session.get(Employee, request.requester_employee_id)
            recipients = [requester] if requester and requester.telegram_user_id else []
            text = f"💬 <b>{display_number}</b> bo'yicha RTM xabari:\n\n{body}"
            keyboard = _keyboard_for(
                "📋 Murojaatni ochish", ReqCB(act="open", rid=request.id).pack()
            )

        targets = [r.telegram_user_id for r in recipients if r and r.telegram_user_id]

    for chat_id in targets:
        await _deliver(chat_id, text, attachments, reply_markup=keyboard)


def _keyboard_for(label: str, callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=callback_data)]]
    )
