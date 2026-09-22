"""The overdue sweep.

Runs on a schedule and does one thing: find requests whose deadline has passed while they
are still open, and tell the three audiences who each need to hear about it differently.

* The RTM group gets a red alarm, because that is where the work is coordinated.
* Each assignee gets a direct nudge with the request in it, because a group message is
  everyone's problem and therefore nobody's.
* The reporter gets an apology that says the work is still moving, because the worst part
  of a late request is not knowing whether it was forgotten.

Warned exactly once per deadline. ``overdue_notified_at`` records it, and moving the
deadline clears it — a warning that repeats every half hour is one people learn to skip.
"""

import logging
from datetime import datetime, timezone

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from afu_shared.assignments import assignees_of
from afu_shared.callbacks import AsgCB, ReqCB
from afu_shared.db import session_scope
from afu_shared.enums import RequestStatus
from afu_shared.group_card import format_duration
from afu_shared.message_links import remember
from afu_shared.models import Employee, Request
from afu_shared.people import short_name
from app.bot_client import get_bot
from app.redis_client import get_redis

logger = logging.getLogger(__name__)

OPEN_STATUSES = (
    RequestStatus.NEW.value,
    RequestStatus.ASSIGNED.value,
    RequestStatus.IN_PROGRESS.value,
)

#: How many to handle in one pass. A backlog is spread over several runs rather than
#: hammering the Bot API — and a scheduled job that suddenly has to send 400 messages is
#: exactly when flood limits bite.
BATCH_LIMIT = 40


async def check_overdue_requests(ctx: dict) -> None:
    """Warn about every request that has just gone past its deadline."""
    now = datetime.now(timezone.utc)

    async with session_scope() as session:
        overdue = list(
            (
                await session.execute(
                    select(Request)
                    .where(
                        Request.deadline_at.isnot(None),
                        Request.deadline_at < now,
                        Request.status.in_(OPEN_STATUSES),
                        Request.overdue_notified_at.is_(None),
                    )
                    .order_by(Request.deadline_at)
                    .limit(BATCH_LIMIT)
                )
            ).scalars()
        )
        if not overdue:
            return

        payloads = []
        for request in overdue:
            requester = await session.get(Employee, request.requester_employee_id)
            team = await assignees_of(session, request.id)
            payloads.append(
                {
                    "id": request.id,
                    "number": request.display_number,
                    "description": request.description,
                    "late": format_duration(request.deadline_at, now) or "yaqinda",
                    "deadline": request.deadline_at.strftime("%d.%m.%Y %H:%M"),
                    "requester_chat": requester.telegram_user_id if requester else None,
                    "assignees": [
                        (row.employee.telegram_user_id, short_name(row.employee.full_name))
                        for row in team
                        if row.employee and row.employee.telegram_user_id
                    ],
                    "names": [short_name(row.employee.full_name) for row in team if row.employee],
                }
            )
            # Marked before anything is sent. If delivery fails halfway the request stays
            # marked, which loses one warning — far better than the alternative, where a
            # crash mid-batch means the whole batch warns again on the next run.
            request.overdue_notified_at = now

    for payload in payloads:
        # Routed through the card refresher rather than posted standalone: the card's
        # headline has to turn red too, and the alarm belongs directly under the card it is
        # about rather than floating loose in the group.
        await ctx["redis"].enqueue_job(
            "refresh_request_cards", payload["id"], _group_alarm(payload)
        )
        await _warn_assignees(payload)
        await _apologise_to_requester(payload)

    logger.info("Overdue sweep warned about %s request(s)", len(payloads))


async def _send(chat_id: int, text: str, request_id: int, keyboard=None) -> None:
    bot = get_bot()
    try:
        sent = await bot.send_message(
            chat_id, text, parse_mode="HTML", reply_markup=keyboard
        )
    except (TelegramForbiddenError, TelegramRetryAfter) as exc:
        logger.warning("Overdue warning to %s not delivered: %s", chat_id, exc)
        return
    await remember(get_redis(), chat_id, sent.message_id, request_id)


def _group_alarm(payload: dict) -> str:
    holders = ", ".join(payload["names"]) if payload["names"] else "hali hech kim olmagan"
    return (
        "🔴🚨 <b>MUDDAT O'TDI</b> 🚨🔴\n"
        "━━━━━━━━━━━━━━\n"
        f"🎫 <b>{payload['number']}</b>\n"
        f"⏰ Muddat edi: <b>{payload['deadline']}</b>\n"
        f"⌛️ Kechikish: <b>{payload['late']}</b>\n"
        f"🛠 Bajaruvchi: {holders}\n\n"
        "❗️ <b>Iltimos, zudlik bilan e'tibor qarating!</b>"
    )


async def _warn_assignees(payload: dict) -> None:
    for chat_id, name in payload["assignees"]:
        text = (
            "🔴 <b>Muddat o'tib ketdi</b>\n\n"
            f"🎫 <b>{payload['number']}</b>\n"
            f"⏰ Muddat edi: {payload['deadline']}\n"
            f"⌛️ Kechikish: <b>{payload['late']}</b>\n\n"
            f"📝 {payload['description']}\n\n"
            "Iltimos, ishni yakunlang yoki murojaatchiga holatni yozib xabar bering."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🛠 Topshiriqni ochish",
                        callback_data=AsgCB(act="open", rid=payload["id"]).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="💬 Murojaatchiga yozish",
                        callback_data=AsgCB(act="msg", rid=payload["id"]).pack(),
                    )
                ],
            ]
        )
        logger.info("Warning %s about overdue request %s", name, payload["number"])
        await _send(chat_id, text, payload["id"], keyboard)


async def _apologise_to_requester(payload: dict) -> None:
    """The reporter's version — an apology, not an alarm.

    They are not the person who can fix it, so a red siren would only worry them. What they
    need to know is that it has not been forgotten and that somebody is on it.
    """
    chat_id = payload["requester_chat"]
    if not chat_id:
        return

    working = (
        f"<b>{', '.join(payload['names'])}</b> ustida ishlamoqda"
        if payload["names"]
        else "RTM xodimlari uni ko'rib chiqmoqda"
    )
    text = (
        "🙏 <b>Uzr so'raymiz</b>\n\n"
        f"🎫 <b>{payload['number']}</b> murojaatingiz belgilangan muddatda "
        "yakunlanmadi.\n\n"
        f"⏰ Muddat edi: {payload['deadline']}\n\n"
        f"Murojaatingiz unutilmadi — {working}. Ish tugashi bilan sizga darhol "
        "xabar beramiz.\n\n"
        "<i>Savolingiz bo'lsa, shu xabarga javob yozing — to'g'ridan-to'g'ri "
        "mas'ul xodimga boradi.</i>"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Murojaatni ochish",
                    callback_data=ReqCB(act="open", rid=payload["id"]).pack(),
                )
            ]
        ]
    )
    await _send(chat_id, text, payload["id"], keyboard)
