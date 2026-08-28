"""RTM-staff screens: assigned request list, detail and internal thread."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.assignments import assignees_of, is_assigned
from afu_shared.inventory import used_on_request
from afu_shared.enums import MessageVisibility, RequestStatus
from afu_shared.labels import status_label
from afu_shared.media import describe_attachments
from afu_shared.models import Employee, Request, RequestAssignee, RequestMessage
from afu_shared.telegram_text import esc
from app.callbacks import AsgCB, InvCB, Nav
from app.keyboards.common import menu_button
from app.services.attachments import attachments_for_request
from app.ui.anchor import Screen
from app.ui.messages import format_message_body
from app.ui.paging import PAGE_SIZE, offset_for, paging_row, total_pages

THREAD_PAGE_SIZE = 5

#: Everything that still needs somebody. WAITING is in the list on purpose: a request
#: parked for a part is still that person's job, and dropping it off their screen is how it
#: gets forgotten until the reporter calls.
OPEN_STATUSES = (
    RequestStatus.ASSIGNED.value,
    RequestStatus.IN_PROGRESS.value,
    RequestStatus.WAITING.value,
)


def _fmt_dt(value) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else "—"


async def build_list(session: AsyncSession, employee: Employee, page: int) -> Screen:
    # Through request_assignees, not Request.assigned_to_employee_id: a colleague who
    # joined a job somebody else picked up first is just as much on it, and reading the
    # single "primary" column would hide their own work from them.
    condition = (
        RequestAssignee.employee_id == employee.id,
        Request.status.in_(OPEN_STATUSES),
    )
    joined = select(Request).join(
        RequestAssignee, RequestAssignee.request_id == Request.id
    )
    total = (
        await session.execute(
            select(func.count())
            .select_from(Request)
            .join(RequestAssignee, RequestAssignee.request_id == Request.id)
            .where(*condition)
        )
    ).scalar_one()

    if total == 0:
        return Screen(
            text="🛠 <b>Mening topshiriqlarim</b>\n\nHozircha ochiq topshiriq yo'q. 👍",
            keyboard=InlineKeyboardMarkup(inline_keyboard=[[menu_button()]]),
        )

    pages = total_pages(total)
    page = min(max(1, page), pages)
    requests = list(
        (
            await session.execute(
                joined.where(*condition)
                # Soonest deadline first; undated work sinks to the bottom.
                .order_by(Request.deadline_at.is_(None), Request.deadline_at)
                .limit(PAGE_SIZE)
                .offset(offset_for(page))
            )
        ).scalars()
    )

    rows = [
        [
            InlineKeyboardButton(
                text=f"{r.display_number} · {_deadline_badge(r)} {status_label(r.status)}",
                callback_data=AsgCB(act="open", rid=r.id, page=page).pack(),
            )
        ]
        for r in requests
    ]

    nav = paging_row(page, pages, lambda p: Nav(to="assign", page=p).pack())
    if nav:
        rows.append(nav)
    rows.append([menu_button()])

    return Screen(
        text=f"🛠 <b>Mening topshiriqlarim</b>\nOchiq: {total} ta",
        keyboard=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def _deadline_badge(request: Request) -> str:
    return request.deadline_at.strftime("%d.%m") if request.deadline_at else "—"


async def build_detail(
    session: AsyncSession, employee: Employee, rid: int, page: int
) -> Screen | None:
    request = await session.get(Request, rid)
    if request is None or not await is_assigned(session, rid, employee.id):
        return None

    requester = await session.get(Employee, request.requester_employee_id)

    lines = [
        f"<b>{request.display_number}</b> · {status_label(request.status)}",
        f"Kategoriya: {esc(request.category.label_uz)}",
        f"Murojaatchi: {esc(requester.full_name) if requester else '—'}",
    ]

    others = [
        row for row in await assignees_of(session, rid) if row.employee_id != employee.id
    ]
    if others:
        names = ", ".join(esc(row.employee.full_name) for row in others if row.employee)
        lines.append(f"🤝 Hamkorlar: {names}")
    if requester and requester.department:
        lines.append(f"Bo'lim: {esc(requester.department.name)}")
    if requester and requester.phone_number:
        lines.append(f"Telefon: {esc(requester.phone_number)}")
    lines.append(f"Muddat: {_fmt_dt(request.deadline_at)}")

    if request.status == RequestStatus.WAITING.value:
        lines.append(
            f"\n⏸ <b>Kutilmoqda:</b> {esc(request.waiting_reason, default='—')}"
            f"\nKutish muddati: {_fmt_dt(request.waiting_until)}"
        )

    if request.status == RequestStatus.RETURNED.value:
        # The reason, right where the buttons used to be. This screen is reachable from an
        # old message long after the request left the list, and "the buttons are gone" is
        # not an explanation anybody can act on.
        lines.append("")
        lines.append(f"🚫 <b>Qaytarib yuborilgan:</b> {_fmt_dt(request.returned_at)}")
        lines.append(f"Sabab: {esc(request.return_reason, default='—')}")

    lines.append(f"\n<b>Tavsif:</b>\n{esc(request.description)}")

    used = await used_on_request(session, rid)
    if used:
        lines.append("\n🔧 <b>Ishlatilgan inventar:</b>")
        for movement in used:
            item = movement.item
            lines.append(f"• {esc(item.name)} — {abs(movement.delta)} {item.unit}")

    files = await attachments_for_request(session, rid)
    if files:
        lines.append(f"\n📎 <b>Materiallar:</b> {describe_attachments(files)}")

    # Closed covers returned as well as finished: reading the thread and the files stays
    # available, because they are the record of what happened, but nothing that changes
    # the request survives on a screen the request has already moved past.
    closed = request.status not in OPEN_STATUSES

    rows: list[list[InlineKeyboardButton]] = []
    if not closed and request.status in (RequestStatus.ASSIGNED.value, RequestStatus.WAITING.value):
        rows.append(
            [
                InlineKeyboardButton(
                    # A parked job resumes rather than starts: the label has to say which,
                    # or pressing it feels like undoing the wait by accident.
                    text="▶️ Davom ettirish"
                    if request.status == RequestStatus.WAITING.value
                    else "▶️ Ishni boshlash",
                    callback_data=AsgCB(act="start", rid=rid, page=page).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="💬 Murojaatchiga", callback_data=AsgCB(act="msg", rid=rid, page=page).pack()
            ),
            InlineKeyboardButton(
                text="🗂 Ichki izoh", callback_data=AsgCB(act="internal", rid=rid, page=page).pack()
            ),
        ]
    )
    thread_row = [
        InlineKeyboardButton(
            text="🧵 Yozishmalar", callback_data=AsgCB(act="thread", rid=rid, page=page).pack()
        )
    ]
    if files:
        thread_row.append(
            InlineKeyboardButton(
                text=f"📎 Materiallar ({len(files)})",
                callback_data=AsgCB(act="files", rid=rid, page=page).pack(),
            )
        )
    rows.append(thread_row)
    if not closed:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Bajarildi",
                    callback_data=AsgCB(act="complete", rid=rid, page=page).pack(),
                )
            ]
        )
    if not closed and request.status != RequestStatus.WAITING.value:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⏸ Inventar kutish",
                    callback_data=InvCB(act="wait", rid=rid).pack(),
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=Nav(to="assign", page=page).pack())]
    )

    return Screen(text="\n".join(lines), keyboard=InlineKeyboardMarkup(inline_keyboard=rows))


async def build_thread(
    session: AsyncSession, employee: Employee, rid: int, page: int, list_page: int
) -> Screen | None:
    request = await session.get(Request, rid)
    if request is None or not await is_assigned(session, rid, employee.id):
        return None

    # Staff see both directions: their internal notes and the requester-facing exchange.
    total = (
        await session.execute(
            select(func.count()).select_from(RequestMessage).where(RequestMessage.request_id == rid)
        )
    ).scalar_one()

    if total == 0:
        return Screen(
            text=f"🧵 <b>{request.display_number}</b> — yozishmalar\n\nHali xabar yo'q.",
            keyboard=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅️ Orqaga",
                            callback_data=AsgCB(act="open", rid=rid, page=list_page).pack(),
                        )
                    ]
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
                .where(RequestMessage.request_id == rid)
                .order_by(RequestMessage.created_at.desc())
                .limit(THREAD_PAGE_SIZE)
                .offset((page - 1) * THREAD_PAGE_SIZE)
            )
        ).all()
    )

    lines = [f"🧵 <b>{request.display_number}</b> — yozishmalar\n"]
    for msg, author in reversed(rows_data):
        internal = msg.visibility == MessageVisibility.INTERNAL.value
        tag = "🗂 [ichki]" if internal else "💬"
        who = "Siz" if author and author.id == employee.id else (author.full_name if author else "—")
        lines.append(
            f"{tag} <b>{who}</b> · <i>{_fmt_dt(msg.created_at)}</i>\n"
            f"{format_message_body(msg)}\n"
        )

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    nav = paging_row(page, pages, lambda p: AsgCB(act="thread", rid=rid, page=p).pack())
    if nav:
        keyboard_rows.append(nav)
    keyboard_rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Orqaga", callback_data=AsgCB(act="open", rid=rid, page=list_page).pack()
            )
        ]
    )

    return Screen(text="\n".join(lines), keyboard=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))
