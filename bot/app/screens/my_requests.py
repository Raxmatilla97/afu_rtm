"""Requester-side screens: list, detail, message thread and rating.

Previously a requester could only see a flat text list of their requests — they could not
open one, read the conversation, or reply. Two-way per-request correspondence was part of
the original product requirements but only ever existed on the staff side.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import MessageVisibility, RequestStatus
from afu_shared.labels import status_label
from afu_shared.media import describe_attachments
from afu_shared.models import Employee, Rating, Request, RequestMessage
from afu_shared.telegram_text import esc
from app.callbacks import Nav, ReqCB
from app.keyboards.common import menu_button
from app.services.attachments import attachments_for_request
from app.ui.anchor import Screen
from app.ui.messages import format_message_body
from app.ui.paging import PAGE_SIZE, offset_for, paging_row, total_pages

THREAD_PAGE_SIZE = 5
#: How many recent messages to preview inside the detail screen itself.
DETAIL_PREVIEW_MESSAGES = 3


def _fmt_dt(value) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else "—"


async def build_list(session: AsyncSession, employee: Employee, page: int) -> Screen:
    total = (
        await session.execute(
            select(func.count())
            .select_from(Request)
            .where(Request.requester_employee_id == employee.id)
        )
    ).scalar_one()

    if total == 0:
        return Screen(
            text="📋 <b>Mening murojaatlarim</b>\n\nSizda hali murojaatlar yo'q.",
            keyboard=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🆕 Yangi murojaat", callback_data=Nav(to="newreq").pack())],
                    [menu_button()],
                ]
            ),
        )

    pages = total_pages(total)
    page = min(max(1, page), pages)
    requests = list(
        (
            await session.execute(
                select(Request)
                .where(Request.requester_employee_id == employee.id)
                .order_by(Request.created_at.desc())
                .limit(PAGE_SIZE)
                .offset(offset_for(page))
            )
        ).scalars()
    )

    rows = [
        [
            InlineKeyboardButton(
                text=f"{r.display_number} · {status_label(r.status)}",
                callback_data=ReqCB(act="open", rid=r.id, page=page).pack(),
            )
        ]
        for r in requests
    ]

    nav = paging_row(page, pages, lambda p: Nav(to="myreq", page=p).pack())
    if nav:
        rows.append(nav)
    rows.append([menu_button()])

    return Screen(
        text=f"📋 <b>Mening murojaatlarim</b>\nJami: {total} ta",
        keyboard=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def build_detail(
    session: AsyncSession, employee: Employee, rid: int, page: int
) -> Screen | None:
    """Detail for one request, or None if it is not this employee's."""
    request = await session.get(Request, rid)
    # Authorization: a requester may only ever open their own request.
    if request is None or request.requester_employee_id != employee.id:
        return None

    assignee = (
        await session.get(Employee, request.assigned_to_employee_id)
        if request.assigned_to_employee_id
        else None
    )

    lines = [
        f"<b>{request.display_number}</b> · {status_label(request.status)}",
        f"Kategoriya: {esc(request.category.label_uz)}",
        f"Yuborilgan: {_fmt_dt(request.created_at)}",
    ]
    if assignee:
        lines.append(f"Mas'ul: {esc(assignee.full_name)}")
    if request.deadline_at:
        lines.append(f"Muddat: {_fmt_dt(request.deadline_at)}")
    lines.append(f"\n<b>Tavsif:</b>\n{esc(request.description)}")

    if request.status == RequestStatus.COMPLETED.value:
        lines.append(f"\n✅ <b>Bajarildi:</b> {_fmt_dt(request.completed_at)}")
        if request.completion_note:
            lines.append(f"Izoh: {esc(request.completion_note)}")

    if request.status == RequestStatus.RETURNED.value:
        # The reporter is the person this state exists for: they are the only one who can
        # do anything about it, and what they need is the sentence explaining what to fix.
        lines.append("")
        lines.append(f"🚫 <b>Qaytarib yuborilgan:</b> {_fmt_dt(request.returned_at)}")
        lines.append(f"Sabab: {esc(request.return_reason, default='—')}")
        lines.append("Kerak bo'lsa, izohni hisobga olib yangi murojaat yuboring.")

    files = await attachments_for_request(session, rid, include_internal=False)
    if files:
        lines.append(f"\n📎 <b>Materiallar:</b> {describe_attachments(files)}")

    messages = await _recent_messages(session, rid, DETAIL_PREVIEW_MESSAGES)
    if messages:
        lines.append("\n<b>Oxirgi xabarlar:</b>")
        for msg, author in reversed(messages):
            who = "Siz" if author and author.id == employee.id else (author.full_name if author else "RTM")
            lines.append(f"• <i>{esc(who)}:</i> {_ellipsis(_preview_of(msg), 80)}")

    rating = (
        await session.execute(select(Rating).where(Rating.request_id == rid))
    ).scalar_one_or_none()

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="💬 Yozish", callback_data=ReqCB(act="reply", rid=rid, page=page).pack()
            ),
            InlineKeyboardButton(
                text="🧵 Yozishmalar", callback_data=ReqCB(act="thread", rid=rid, page=page).pack()
            ),
        ]
    ]
    if files:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📎 Materiallarni ko'rish ({len(files)})",
                    callback_data=ReqCB(act="files", rid=rid, page=page).pack(),
                )
            ]
        )
    if request.status == RequestStatus.COMPLETED.value and rating is None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⭐ Baholash", callback_data=ReqCB(act="rate", rid=rid, page=page).pack()
                )
            ]
        )
    elif rating is not None:
        lines.append(f"\n⭐ Bahoyingiz: {rating.score}/5")

    rows.append(
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=Nav(to="myreq", page=page).pack())]
    )

    return Screen(text="\n".join(lines), keyboard=InlineKeyboardMarkup(inline_keyboard=rows))


async def build_thread(
    session: AsyncSession, employee: Employee, rid: int, page: int, list_page: int
) -> Screen | None:
    request = await session.get(Request, rid)
    if request is None or request.requester_employee_id != employee.id:
        return None

    # Internal RTM notes must never reach the requester — this filter is the security core
    # of the whole feature.
    visible = RequestMessage.visibility == MessageVisibility.TO_REQUESTER.value

    total = (
        await session.execute(
            select(func.count())
            .select_from(RequestMessage)
            .where(RequestMessage.request_id == rid, visible)
        )
    ).scalar_one()

    if total == 0:
        return Screen(
            text=f"🧵 <b>{request.display_number}</b> — yozishmalar\n\nHali xabar yo'q.",
            keyboard=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💬 Yozish",
                            callback_data=ReqCB(act="reply", rid=rid, page=list_page).pack(),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ Orqaga",
                            callback_data=ReqCB(act="open", rid=rid, page=list_page).pack(),
                        )
                    ],
                ]
            ),
        )

    pages = max(1, (total + THREAD_PAGE_SIZE - 1) // THREAD_PAGE_SIZE)
    page = min(max(1, page), pages)

    rows_data = list(
        (
            await session.execute(
                select(RequestMessage, Employee)
                .outerjoin(Employee, RequestMessage.author_employee_id == Employee.id)
                .where(RequestMessage.request_id == rid, visible)
                .order_by(RequestMessage.created_at.desc())
                .limit(THREAD_PAGE_SIZE)
                .offset((page - 1) * THREAD_PAGE_SIZE)
            )
        ).all()
    )

    lines = [f"🧵 <b>{request.display_number}</b> — yozishmalar\n"]
    for msg, author in reversed(rows_data):
        who = "👤 Siz" if author and author.id == employee.id else f"🛠 {author.full_name if author else 'RTM'}"
        lines.append(f"{who} · <i>{_fmt_dt(msg.created_at)}</i>\n{format_message_body(msg)}\n")

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    nav = paging_row(
        page, pages, lambda p: ReqCB(act="thread", rid=rid, page=p, score=list_page).pack()
    )
    if nav:
        keyboard_rows.append(nav)
    keyboard_rows.append(
        [
            InlineKeyboardButton(
                text="💬 Yozish", callback_data=ReqCB(act="reply", rid=rid, page=list_page).pack()
            )
        ]
    )
    keyboard_rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Orqaga", callback_data=ReqCB(act="open", rid=rid, page=list_page).pack()
            )
        ]
    )

    return Screen(text="\n".join(lines), keyboard=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))


def build_rating_screen(rid: int, page: int, display_number: str) -> Screen:
    return Screen(
        text=(
            f"⭐ <b>{display_number}</b>\n\n"
            "Xizmat sifatini baholang (1 — yomon, 5 — a'lo):"
        ),
        keyboard=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⭐" * score,
                        callback_data=ReqCB(act="rate_set", rid=rid, page=page, score=score).pack(),
                    )
                ]
                for score in range(1, 6)
            ]
            + [
                [
                    InlineKeyboardButton(
                        text="⬅️ Orqaga", callback_data=ReqCB(act="open", rid=rid, page=page).pack()
                    )
                ]
            ]
        ),
    )


async def _recent_messages(
    session: AsyncSession, rid: int, limit: int
) -> list[tuple[RequestMessage, Employee | None]]:
    return list(
        (
            await session.execute(
                select(RequestMessage, Employee)
                .outerjoin(Employee, RequestMessage.author_employee_id == Employee.id)
                .where(
                    RequestMessage.request_id == rid,
                    RequestMessage.visibility == MessageVisibility.TO_REQUESTER.value,
                )
                .order_by(RequestMessage.created_at.desc())
                .limit(limit)
            )
        ).all()
    )


def _preview_of(message: RequestMessage) -> str:
    """One plain line for the detail screen — no markup, since it is already inside an
    italic run and nested tags would break the parse."""
    if message.body:
        return message.body
    if message.attachments:
        return describe_attachments(message.attachments)
    return "—"


def _ellipsis(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
