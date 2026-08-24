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

RULE = "━━━━━━━━━━━━━━"

#: Headline per status. The card's whole state has to be readable from the first line,
#: because that is all anyone scrolling a busy group actually reads.
_HEADLINES = {
    RequestStatus.NEW.value: "🆕 <b>YANGI MUROJAAT</b>",
    RequestStatus.ASSIGNED.value: "🙋 <b>QABUL QILINDI</b>",
    RequestStatus.IN_PROGRESS.value: "⚡️ <b>ISH KETMOQDA</b>",
    RequestStatus.COMPLETED.value: "✅ <b>BAJARILDI</b>",
    RequestStatus.CANCELLED.value: "❌ <b>BEKOR QILINDI</b>",
}

_MEDALS = ("🥇", "🥈", "🥉")


def _duration(start: datetime | None, end: datetime | None) -> str | None:
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
    return _duration(created_at, datetime.now(timezone.utc))


def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else "—"


def build_card_text(
    request: Request,
    requester: Employee | None,
    assignees: list[RequestAssignee],
    attachments: list[RequestAttachment],
    ratings: list[Rating] | None = None,
) -> str:
    lines = [
        _HEADLINES.get(request.status, "📋 <b>MUROJAAT</b>"),
        RULE,
        f"🎫 <b>{request.display_number}</b> · "
        f"{request.category.label_uz if request.category else '—'}",
        "",
    ]

    if requester:
        lines.append(f"👤 <b>{requester.full_name}</b>")
        if requester.department:
            lines.append(f"🏢 {requester.department.name}")
        if requester.phone_number:
            lines.append(f"📞 <code>{requester.phone_number}</code>")
        lines.append("")

    lines.append(f"📝 {request.description}")

    if attachments:
        lines.append(f"\n📎 {describe_attachments(attachments)}")

    lines.append("")
    if assignees:
        lines.append("🛠 <b>Bajaruvchilar:</b>")
        for index, row in enumerate(assignees):
            badge = _MEDALS[index] if index < len(_MEDALS) else "•"
            name = row.employee.full_name if row.employee else f"#{row.employee_id}"
            lead = " <i>(mas'ul)</i>" if row.is_primary else ""
            lines.append(f"{badge} {name}{lead}")
    elif request.status == RequestStatus.CANCELLED.value:
        lines.append("❌ Bu murojaat bekor qilingan.")
    else:
        waiting = _age(request.created_at)
        lines.append("⏳ <b>Hali hech kim olmadi</b>")
        if waiting:
            lines.append(f"<i>Kutmoqda: {waiting}</i>")

    if request.deadline_at and request.status != RequestStatus.COMPLETED.value:
        lines.append(f"\n⏰ Muddat: {_fmt_dt(request.deadline_at)}")

    if request.status == RequestStatus.COMPLETED.value:
        spent = _duration(request.assigned_at or request.created_at, request.completed_at)
        lines.append(f"\n🏁 Yakunlandi: {_fmt_dt(request.completed_at)}")
        if spent:
            lines.append(f"⏱ Sarflangan vaqt: <b>{spent}</b>")
        if request.completion_note:
            lines.append(f"💬 {request.completion_note}")

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
    """
    rows: list[list[InlineKeyboardButton]] = []
    rid = request.id
    is_open = request.status in (
        RequestStatus.NEW.value,
        RequestStatus.ASSIGNED.value,
        RequestStatus.IN_PROGRESS.value,
    )

    if is_open:
        take_label = "🤝 Men ham qo'shilaman" if assignees else "✋ Men bajaraman"
        rows.append(
            [InlineKeyboardButton(text=take_label, callback_data=GrpCB(act="take", rid=rid).pack())]
        )
        if assignees:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="🚪 Voz kechaman",
                        callback_data=GrpCB(act="leave", rid=rid).pack(),
                    )
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
