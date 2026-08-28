"""The request card posted into an RTM group chat.

One card per request, edited in place for its whole life. That constraint shapes the whole
design: the card has to read well at every stage, because it is the same message that
announced the job, showed who took it, and finally reports it done. A group that instead
received four separate messages per request would be unreadable by mid-morning.

Built here rather than in the bot because the worker posts and edits these cards, while the
bot answers the buttons on them — and a button whose card the two services disagree about
is a support ticket nobody can reproduce.
"""

from datetime import datetime, timezone

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from afu_shared.callbacks import GrpCB
from afu_shared.enums import RequestStatus
from afu_shared.media import describe_attachments
from afu_shared.models import Employee, Rating, Request, RequestAssignee, RequestAttachment
from afu_shared.settings import settings
from afu_shared.telegram_text import esc

RULE = "━━━━━━━━━━━━━━"

#: Headline per status. The card's whole state has to be readable from the first line,
#: because that is all anyone scrolling a busy group actually reads.
_HEADLINES = {
    RequestStatus.NEW.value: "🆕 <b>YANGI MUROJAAT</b>",
    RequestStatus.ASSIGNED.value: "🙋 <b>QABUL QILINDI</b>",
    RequestStatus.IN_PROGRESS.value: "⚡️ <b>ISH KETMOQDA</b>",
    RequestStatus.WAITING.value: "⏸ <b>QISM KUTILMOQDA</b>",
    RequestStatus.COMPLETED.value: "✅ <b>BAJARILDI</b>",
    RequestStatus.CANCELLED.value: "❌ <b>BEKOR QILINDI</b>",
    RequestStatus.RETURNED.value: "🚫 <b>QAYTARIB YUBORILDI</b>",
}

#: Overrides the status headline once the deadline has passed. Telegram has no colours, so
#: urgency has to be carried by the one visual channel a chat does have.
OVERDUE_HEADLINE = "🔴🚨 <b>MUDDAT O'TDI</b>"

_MEDALS = ("🥇", "🥈", "🥉")


def is_overdue(request: Request, *, now: datetime | None = None) -> bool:
    """Past its deadline and still not finished.

    A cancelled or completed request is never overdue, however long ago its deadline was —
    it is simply done, and flagging it would be noise.
    """
    if request.deadline_at is None:
        return False
    # A parked request is not late: the delay belongs to the supply chain, and shouting at
    # the person holding it changes nothing they can act on.
    if request.status not in (
        RequestStatus.NEW.value,
        RequestStatus.ASSIGNED.value,
        RequestStatus.IN_PROGRESS.value,
    ):
        return False
    return request.deadline_at < (now or datetime.now(timezone.utc))


def format_duration(start: datetime | None, end: datetime | None) -> str | None:
    if not start or not end:
        return None
    minutes = int((end - start).total_seconds() // 60)
    if minutes < 1:
        return "1 daqiqadan kam"
    if minutes < 60:
        return f"{minutes} daqiqa"
    hours, rest = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} soat {rest} daqiqa" if rest else f"{hours} soat"
    days, hours = divmod(hours, 24)
    return f"{days} kun {hours} soat" if hours else f"{days} kun"


def _age(created_at: datetime | None) -> str | None:
    if not created_at:
        return None
    return format_duration(created_at, datetime.now(timezone.utc))


def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else "—"


def build_card_text(
    request: Request,
    requester: Employee | None,
    assignees: list[RequestAssignee],
    attachments: list[RequestAttachment],
    ratings: list[Rating] | None = None,
) -> str:
    overdue = is_overdue(request)
    lines = [
        OVERDUE_HEADLINE if overdue else _HEADLINES.get(request.status, "📋 <b>MUROJAAT</b>"),
        RULE,
        f"🎫 <b>{request.display_number}</b> · "
        f"{esc(request.category.label_uz if request.category else None, default='—')}",
        "",
    ]

    if requester:
        lines.append(f"👤 <b>{esc(requester.full_name)}</b>")
        if requester.department:
            lines.append(f"🏢 {esc(requester.department.name)}")
        if requester.phone_number:
            lines.append(f"📞 <code>{esc(requester.phone_number)}</code>")
        lines.append("")

    lines.append(f"📝 {esc(request.description)}")

    if attachments:
        lines.append(f"\n📎 {describe_attachments(attachments)}")

    lines.append("")
    if assignees:
        lines.append("🛠 <b>Bajaruvchilar:</b>")
        for index, row in enumerate(assignees):
            badge = _MEDALS[index] if index < len(_MEDALS) else "•"
            name = esc(row.employee.full_name) if row.employee else f"#{row.employee_id}"
            lead = " <i>(mas'ul)</i>" if row.is_primary else ""
            lines.append(f"{badge} {name}{lead}")
    elif request.status == RequestStatus.CANCELLED.value:
        lines.append("❌ Bu murojaat bekor qilingan.")
    elif request.status == RequestStatus.RETURNED.value:
        lines.append("🚫 Bu murojaat qaytarib yuborilgan.")
    else:
        waiting = _age(request.created_at)
        lines.append("⏳ <b>Hali hech kim olmadi</b>")
        if waiting:
            lines.append(f"<i>Kutmoqda: {waiting}</i>")

    if overdue:
        late = format_duration(request.deadline_at, datetime.now(timezone.utc))
        lines.append(f"\n🔴 <b>Muddat: {_fmt_dt(request.deadline_at)}</b>")
        if late:
            lines.append(f"🚨 <b>{late} kechikdi!</b>")
    elif request.deadline_at and request.status != RequestStatus.COMPLETED.value:
        lines.append(f"\n⏰ Muddat: {_fmt_dt(request.deadline_at)}")

    if request.status == RequestStatus.RETURNED.value:
        # On the card whether or not anybody had taken the job: the group is where the next
        # person would otherwise pick up a request RTM has already sent back.
        lines.append("")
        lines.append(f"🚫 <b>Qaytarilgan sabab:</b> {esc(request.return_reason, default='—')}")
        lines.append(f"<i>{_fmt_dt(request.returned_at)}</i>")

    if request.status == RequestStatus.COMPLETED.value:
        spent = format_duration(request.assigned_at or request.created_at, request.completed_at)
        lines.append(f"\n🟢 Yakunlandi: {_fmt_dt(request.completed_at)}")
        if spent:
            lines.append(f"⏱ Sarflangan vaqt: <b>{spent}</b>")
        if request.completion_note:
            lines.append(f"💬 {esc(request.completion_note)}")

    scores = [r.score for r in (ratings or [])]
    if scores:
        average = sum(scores) / len(scores)
        filled = round(average)
        lines.append(f"\n{'⭐' * filled}{'☆' * (5 - filled)} <b>{average:.0f}/5</b>")

    return "\n".join(lines)


def build_card_keyboard(
    request: Request, assignees: list[RequestAssignee], attachments: list[RequestAttachment]
) -> InlineKeyboardMarkup:
    """Buttons under the card.

    The "take it" button stays available after somebody has already taken the job — that is
    the point of co-assignment — but disappears once the work is finished or cancelled,
    where joining would mean nothing.

    There is deliberately no "give it back". Taking a request is a commitment somebody made
    in front of the whole group, and a one-tap undo turns it into a guess. Removing an
    assignee is a supervisor's decision, taken on the web where it is recorded.

    "Tayinlash" is shown to everyone rather than only to supervisors: a card is one message
    seen by the whole group, so its buttons cannot vary per viewer. The check happens when
    it is pressed, and anyone else gets a pop-up only they see.
    """
    rows: list[list[InlineKeyboardButton]] = []
    rid = request.id
    is_open = request.status in (
        RequestStatus.NEW.value,
        RequestStatus.ASSIGNED.value,
        RequestStatus.IN_PROGRESS.value,
        RequestStatus.WAITING.value,
    )

    if is_open:
        take_label = "🤝 Men ham qo'shilaman" if assignees else "✋ Men bajaraman"
        rows.append(
            [
                InlineKeyboardButton(
                    text=take_label, callback_data=GrpCB(act="take", rid=rid).pack()
                ),
                InlineKeyboardButton(
                    text="👤 Tayinlash", callback_data=GrpCB(act="assign", rid=rid).pack()
                ),
            ]
        )

    extras: list[InlineKeyboardButton] = []
    if attachments:
        extras.append(
            InlineKeyboardButton(
                text=f"📎 Materiallar ({len(attachments)})",
                callback_data=GrpCB(act="files", rid=rid).pack(),
            )
        )
    deep_link = _bot_deep_link(rid)
    if deep_link:
        extras.append(InlineKeyboardButton(text="💬 Botda ochish", url=deep_link))
    if extras:
        rows.append(extras)

    return InlineKeyboardMarkup(inline_keyboard=rows)


#: Names per page in the picker. Two columns of four still fit a phone without the captions
#: being cut in half.
PICKER_PAGE_SIZE = 8


def build_picker_keyboard(
    request_id: int,
    staff: list[Employee],
    assigned_ids: set[int],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """The staff list, drawn onto the card itself.

    Swapping the card's own buttons rather than posting a chooser message is what keeps the
    group clean: picking somebody adds nothing to the chat and leaves nothing behind if the
    supervisor changes their mind and presses back.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for index in range(0, len(staff), 2):
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅ " if person.id in assigned_ids else "") + person.full_name,
                    callback_data=GrpCB(act="pick", rid=request_id, eid=person.id).pack(),
                )
                for person in staff[index : index + 2]
            ]
        )

    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=GrpCB(act="assign", rid=request_id, page=page - 1).pack(),
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page}/{total_pages}",
                callback_data=GrpCB(act="assign", rid=request_id, page=page).pack(),
            )
        )
        if page < total_pages:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=GrpCB(act="assign", rid=request_id, page=page + 1).pack(),
                )
            )
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Orqaga", callback_data=GrpCB(act="back", rid=request_id).pack()
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _bot_deep_link(request_id: int) -> str | None:
    """A link that opens this request inside the bot's private chat.

    Everything that needs typing — the completion report, a reply to the reporter, an
    internal note — belongs in a DM, not in the group. This is the bridge between the two,
    and it is why the group card never tries to be a full workspace.
    """
    username = settings.telegram_bot_username.strip().lstrip("@")
    if not username:
        return None
    return f"https://t.me/{username}?start=req_{request_id}"
