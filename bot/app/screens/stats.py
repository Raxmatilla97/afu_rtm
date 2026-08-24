"""Statistics — four tabs that swap in place on the anchor message.

A chat has no room for a dashboard, and the previous single screen answered every question
at once and none of them well. Splitting it into tabs the reader chooses, and drawing the
numbers as bars rather than listing them, turns the same data into something you can
actually read on a phone: a bar chart made of block characters shows the shape of a month
at a glance, where "• 2026-03: 14 ta" does not.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import RequestStatus
from afu_shared.labels import status_label
from afu_shared.models import Employee, Rating, Request, RequestAssignee
from app.callbacks import StatCB
from app.keyboards.common import menu_button
from app.ui.anchor import Screen

MONTHS_SHOWN = 6
TOP_STAFF_SHOWN = 7
#: Widest bar, in characters. Chosen so the longest line still fits a narrow phone once the
#: label and the count are prepended.
BAR_WIDTH = 12

_MONTH_NAMES_UZ = (
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
)

_TABS = (
    ("overview", "📊 Umumiy"),
    ("mine", "👤 Men"),
    ("work", "🛠 Ishim"),
    ("top", "🏆 Top"),
)


def _bar(value: int, peak: int, width: int = BAR_WIDTH) -> str:
    """A proportional bar. An existing but tiny value still gets one block, so "1" never
    renders as an empty line indistinguishable from zero."""
    if peak <= 0:
        return ""
    filled = round(width * value / peak)
    if value > 0:
        filled = max(1, filled)
    return "█" * filled + "░" * (width - filled)


def _month_label(value) -> str:
    return f"{_MONTH_NAMES_UZ[value.month - 1]} {value.year % 100:02d}"


def _tab_keyboard(current: str, *, show_work: bool) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(
            # The active tab is marked rather than removed: a tab strip that changes
            # shape as you move through it is disorienting.
            text=f"• {title} •" if key == current else title,
            callback_data=StatCB(view=key).pack(),
        )
        for key, title in _TABS
        if key != "work" or show_work
    ]
    # Two rows: four captions on one row are truncated on narrow screens.
    half = (len(row) + 1) // 2
    return InlineKeyboardMarkup(inline_keyboard=[row[:half], row[half:], [menu_button()]])


async def build_stats(
    session: AsyncSession, employee: Employee, view: str = "overview"
) -> Screen:
    if view == "mine":
        text = await _mine(session, employee)
    elif view == "work" and employee.is_rtm_staff:
        text = await _work(session, employee)
    elif view == "top":
        text = await _top(session)
    else:
        view = "overview"
        text = await _overview(session)

    return Screen(text=text, keyboard=_tab_keyboard(view, show_work=employee.is_rtm_staff))


async def _overview(session: AsyncSession) -> str:
    counts = dict(
        (
            await session.execute(
                select(Request.status, func.count()).group_by(Request.status)
            )
        ).all()
    )
    total = sum(counts.values())

    lines = ["📊 <b>Umumiy statistika</b>", ""]
    if total == 0:
        lines.append("Hozircha murojaatlar yo'q.")
        return "\n".join(lines)

    lines.append(f"Jami murojaatlar: <b>{total}</b> ta\n")
    peak = max(counts.values())
    for status in RequestStatus:
        value = counts.get(status.value, 0)
        if value == 0:
            continue
        lines.append(f"{status_label(status.value)}")
        lines.append(f"<code>{_bar(value, peak)}</code> {value} ta")

    month = func.date_trunc("month", Request.completed_at).label("month")
    monthly = list(
        (
            await session.execute(
                select(month, func.count().label("total"))
                .where(Request.status == RequestStatus.COMPLETED.value)
                .group_by(month)
                .order_by(month.desc())
                .limit(MONTHS_SHOWN)
            )
        ).all()
    )
    if monthly:
        lines.append("\n<b>Oylar bo'yicha bajarilgan</b>")
        peak_month = max(count for _, count in monthly)
        for month_value, count in reversed(monthly):
            lines.append(
                f"<code>{_bar(count, peak_month)}</code> {count:>3} · {_month_label(month_value)}"
            )

    return "\n".join(lines)


async def _mine(session: AsyncSession, employee: Employee) -> str:
    counts = dict(
        (
            await session.execute(
                select(Request.status, func.count())
                .where(Request.requester_employee_id == employee.id)
                .group_by(Request.status)
            )
        ).all()
    )
    total = sum(counts.values())

    lines = ["👤 <b>Mening murojaatlarim</b>", ""]
    if total == 0:
        lines.append("Siz hali murojaat yubormagansiz.")
        return "\n".join(lines)

    lines.append(f"Jami: <b>{total}</b> ta\n")
    peak = max(counts.values())
    for status in RequestStatus:
        value = counts.get(status.value, 0)
        if value == 0:
            continue
        lines.append(f"{status_label(status.value)}")
        lines.append(f"<code>{_bar(value, peak)}</code> {value} ta")

    given = (
        await session.execute(
            select(func.count(), func.avg(Rating.score)).where(
                Rating.rated_by_employee_id == employee.id
            )
        )
    ).one()
    if given[0]:
        lines.append(f"\n⭐ Siz {given[0]} ta baho qo'ygansiz")
        lines.append(f"O'rtacha: <b>{float(given[1]):.2f}</b> / 5")

    return "\n".join(lines)


async def _work(session: AsyncSession, employee: Employee) -> str:
    # Counted through the assignee table, so work shared with a colleague still counts as
    # this person's work.
    def mine(*conditions):
        return (
            select(func.count())
            .select_from(RequestAssignee)
            .join(Request, Request.id == RequestAssignee.request_id)
            .where(RequestAssignee.employee_id == employee.id, *conditions)
        )

    done = (
        await session.execute(mine(Request.status == RequestStatus.COMPLETED.value))
    ).scalar_one()
    open_now = (
        await session.execute(
            mine(
                Request.status.in_(
                    (RequestStatus.ASSIGNED.value, RequestStatus.IN_PROGRESS.value)
                )
            )
        )
    ).scalar_one()

    lines = [
        "🛠 <b>Mening ishim</b>",
        "",
        f"Ochiq topshiriqlar: <b>{open_now}</b> ta",
        f"Bajarilgan: <b>{done}</b> ta",
    ]

    scores = dict(
        (
            await session.execute(
                select(Rating.score, func.count())
                .where(Rating.rated_employee_id == employee.id)
                .group_by(Rating.score)
            )
        ).all()
    )
    if scores:
        rated = sum(scores.values())
        average = sum(score * n for score, n in scores.items()) / rated
        lines.append(f"\n⭐ O'rtacha baho: <b>{average:.2f}</b> / 5 ({rated} ta baho)")
        peak = max(scores.values())
        for score in range(5, 0, -1):
            value = scores.get(score, 0)
            lines.append(f"{score}⭐ <code>{_bar(value, peak)}</code> {value}")
    else:
        lines.append("\n⭐ Hali baho olmagansiz.")

    return "\n".join(lines)


async def _top(session: AsyncSession) -> str:
    """Leaderboard by completed work, with the average score alongside.

    Ordered by volume rather than by score on purpose: an average over two ratings would
    otherwise outrank a colleague who closed forty jobs.

    Counted through ``request_assignees``, so a job two people did together counts once for
    each of them. The join to ``ratings`` is on the employee as well as the request —
    ratings now fan out to every assignee, and matching on the request alone would pull in
    a colleague's row and count the same completion twice.
    """
    completed = func.count(Request.id).label("completed")
    rows = list(
        (
            await session.execute(
                select(
                    Employee.full_name,
                    completed,
                    func.avg(Rating.score).label("avg_score"),
                )
                .select_from(RequestAssignee)
                .join(Request, Request.id == RequestAssignee.request_id)
                .join(Employee, Employee.id == RequestAssignee.employee_id)
                .outerjoin(
                    Rating,
                    and_(
                        Rating.request_id == Request.id,
                        Rating.rated_employee_id == RequestAssignee.employee_id,
                    ),
                )
                .where(Request.status == RequestStatus.COMPLETED.value)
                .group_by(Employee.id, Employee.full_name)
                .order_by(completed.desc())
                .limit(TOP_STAFF_SHOWN)
            )
        ).all()
    )

    lines = ["🏆 <b>Top xodimlar</b>", ""]
    if not rows:
        lines.append("Hali bajarilgan murojaat yo'q.")
        return "\n".join(lines)

    medals = ("🥇", "🥈", "🥉")
    peak = rows[0][1]
    for index, (name, count, avg_score) in enumerate(rows):
        badge = medals[index] if index < len(medals) else f"{index + 1}."
        score = f" · ⭐ {float(avg_score):.1f}" if avg_score is not None else ""
        lines.append(f"{badge} <b>{name}</b>{score}")
        lines.append(f"<code>{_bar(count, peak)}</code> {count} ta")

    return "\n".join(lines)
