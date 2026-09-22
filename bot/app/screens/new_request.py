"""New-request flow screens.

Two flows live here, and they diverge only at the end. Everybody fills in a category, a
description and optionally some files. A **Boshliq** — see ``Employee.can_file_managed_request``
— then gets two more steps before the card is published: how long the job has, and who is
on it. What they file is a directive, and it lands in the RTM group looking like one.

An employee flagged only Admin takes the ordinary path and is told why, on the first screen,
rather than being left to wonder where the extra buttons went.
"""

from datetime import datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Category, Employee
from afu_shared.people import short_name
from afu_shared.telegram_text import esc
from app.callbacks import CatCB, FlowCB, Nav, ReqCB
from app.keyboards.common import menu_button
from app.ui.anchor import Screen

CANCEL_ROW = [InlineKeyboardButton(text="✖️ Bekor qilish", callback_data=Nav(to="menu").pack())]

#: The deadlines offered in the directive flow, as whole units of time from now. Kept in
#: step with DEADLINE_PRESETS on the web's new-request page: a directive issued from a
#: phone and one issued from a desk have to mean the same thing.
DEADLINE_CHOICES: tuple[tuple[str, int], ...] = (
    ("1 soat", 60),
    ("2 soat", 120),
    ("6 soat", 360),
    ("1 kun", 24 * 60),
    ("2 kun", 48 * 60),
    ("1 hafta", 7 * 24 * 60),
)

#: Names per page of the staff picker. Two columns of four — the same shape the group
#: card's picker uses, so the two do not feel like different products.
STAFF_PAGE_SIZE = 8

#: Shown to an employee who is an Admin but not a Boshliq, on the first screen of the flow.
#: Printed where the extra options would have been rather than as a pop-up they dismiss
#: without reading — the point is that they understand the rule, not that they acknowledge it.
ADMIN_ONLY_NOTE = (
    "\n\n⚠️ <b>Diqqat:</b> sizda <b>Admin</b> roli bor, lekin <b>Boshliq</b> roli yo'q.\n"
    "Shuning uchun <b>muddat</b> va <b>bajaruvchi</b> belgilash bandlari chiqmaydi — "
    "murojaatingiz oddiy tartibda navbatga tushadi va xodimlar o'zlari oladi.\n"
    "<i>Topshiriq berish — RTM boshlig'ining huquqi.</i>"
)


def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else "—"


async def build_category_screen(session: AsyncSession, employee: Employee | None = None) -> Screen:
    categories = list(
        (
            await session.execute(
                select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order)
            )
        ).scalars()
    )
    rows = [
        [InlineKeyboardButton(text=c.label_uz, callback_data=CatCB(slug=c.slug).pack())]
        for c in categories
    ]
    rows.append(CANCEL_ROW)

    if employee is not None and employee.can_file_managed_request:
        role = "ADMIN" if employee.is_admin else "BOSHLIQ"
        header = (
            f"👑 <b>YANGI TOPSHIRIQ</b> · <b>{role}</b>\n"
            f"{'━' * 14}\n\n"
            "Tavsifni yozganingizdan so'ng <b>bajarish muddati</b> va "
            "<b>mas'ul xodimlar</b>ni ham belgilaysiz.\n\n"
            "Muammo turini tanlang:"
        )
    else:
        header = "🆕 <b>Yangi murojaat</b>\n\nMuammo turini tanlang:"
        if employee is not None and employee.is_admin:
            header += ADMIN_ONLY_NOTE

    return Screen(text=header, keyboard=InlineKeyboardMarkup(inline_keyboard=rows))


def build_description_screen(category_label: str) -> Screen:
    return Screen(
        text=(
            f"🆕 <b>Yangi murojaat</b>\nTuri: {category_label}\n\n"
            "Muammoni tushuntiring — <b>yozib</b> yoki <b>ovozli xabar</b>, "
            "<b>video</b>, <b>aylana video</b> yuborib.\n"
            "<i>Masalan: 3-qavat 305-xonadagi printer qog'oz tortmayapti.</i>"
        ),
        keyboard=InlineKeyboardMarkup(inline_keyboard=[CANCEL_ROW]),
    )


def build_attachment_choice_screen(category_label: str, description: str) -> Screen:
    return Screen(
        text=(
            f"🆕 <b>Yangi murojaat</b>\nTuri: {category_label}\n\n"
            f"<b>Tavsif:</b>\n{esc(description)}\n\n"
            "Fayl biriktirasizmi? (rasm, video, ovozli xabar, hujjat)"
        ),
        keyboard=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📎 Ha", callback_data=FlowCB(act="attach_yes").pack()
                    ),
                    InlineKeyboardButton(
                        text="➡️ Yo'q, yuborish", callback_data=FlowCB(act="attach_no").pack()
                    ),
                ],
                CANCEL_ROW,
            ]
        ),
    )


def build_media_screen(display_number: str, summary: str) -> Screen:
    """The prompt that follows every uploaded file.

    Re-rendered with ``force_new`` after each upload so it lands *underneath* the file the
    user just sent — when it was edited in place it stayed wherever the flow began, and the
    "Tayyor" button scrolled out of reach as the uploads piled up.
    """
    counter = f"\n\n<b>Qabul qilindi:</b> {summary}" if summary else ""
    return Screen(
        text=(
            f"📎 <b>{display_number}</b>{counter}\n\n"
            "Yana fayl yuborishingiz mumkin — rasm, video, ovozli xabar yoki hujjat.\n"
            "Tugagach «✅ Tayyor» ni bosing."
        ),
        keyboard=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Tayyor", callback_data=FlowCB(act="media_done").pack())]
            ]
        ),
    )


def build_deadline_screen(display_number: str, role: str, summary: str) -> Screen:
    """Step one of the directive: how long the job has.

    Offered as whole units of time rather than a date to type. A deadline picked from six
    buttons is set in one tap on a phone; one typed as "25.09.2026 14:00" is three chances
    to get the format wrong, and the flow has no way to tell a typo from a real date.
    """
    counter = f"\n📎 Biriktirildi: {summary}" if summary else ""
    rows = [
        [
            InlineKeyboardButton(
                text=f"⏱ {label}", callback_data=FlowCB(act="dl", n=minutes).pack()
            )
            for label, minutes in DEADLINE_CHOICES[index : index + 2]
        ]
        for index in range(0, len(DEADLINE_CHOICES), 2)
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="⏭ Muddatsiz davom etish", callback_data=FlowCB(act="dl", n=0).pack()
            )
        ]
    )
    rows.append(CANCEL_ROW)

    return Screen(
        text=(
            f"👑 <b>{role} TOPSHIRIG'I</b>\n"
            f"{'━' * 14}\n"
            f"🎫 <b>{display_number}</b>{counter}\n\n"
            "⏱ <b>Bajarish muddatini tanlang</b>\n"
            "<i>Hozirdan boshlab hisoblanadi. Muddat o'tsa, guruhdagi kartochka qizil "
            "«MUDDAT O'TDI» holatiga o'tadi va xodimlarga eslatma boradi.</i>"
        ),
        keyboard=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def build_assignees_screen(
    display_number: str,
    role: str,
    deadline_at: datetime | None,
    staff: list[Employee],
    chosen_ids: list[int],
    page: int,
    pages: int,
) -> Screen:
    """Step two: who is on it.

    Multi-select, and the order matters — the first name tapped is the mas'ul. Tapping a
    chosen name again removes it, which is the only undo this screen needs; everything else
    is one more tap away.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for index in range(0, len(staff), 2):
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{'⭐' if chosen_ids and chosen_ids[0] == person.id else '✅' if person.id in chosen_ids else ''}"
                        f"{short_name(person.full_name)}"
                    ),
                    callback_data=FlowCB(act="pick", eid=person.id, page=page).pack(),
                )
                for person in staff[index : index + 2]
            ]
        )

    if pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 1:
            nav.append(
                InlineKeyboardButton(
                    text="⬅️", callback_data=FlowCB(act="page", page=page - 1).pack()
                )
            )
        nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="noop"))
        if page < pages:
            nav.append(
                InlineKeyboardButton(
                    text="➡️", callback_data=FlowCB(act="page", page=page + 1).pack()
                )
            )
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text=("📨 Topshiriqni yuborish" if chosen_ids else "⏭ Tayinlamasdan yuborish"),
                callback_data=FlowCB(act="send").pack(),
            )
        ]
    )
    rows.append(CANCEL_ROW)

    # Names for the picks visible on this page; the rest are counted rather than named.
    # The picker is paged, and resolving an off-page name would mean another query for a
    # line that is already saying the number out loud.
    on_page = [
        esc(short_name(person.full_name))
        for person_id in chosen_ids
        for person in staff
        if person.id == person_id
    ]
    if chosen_ids:
        elsewhere = len(chosen_ids) - len(on_page)
        listed = ", ".join(on_page) if on_page else ""
        if elsewhere:
            listed = f"{listed}, +{elsewhere} ta" if listed else f"{elsewhere} ta (boshqa sahifada)"
        chosen_line = f"\n🛠 <b>Tanlandi ({len(chosen_ids)}):</b> {listed}"
    else:
        chosen_line = "\n🛠 <i>Hech kim tanlanmadi — topshiriq guruhga «egasiz» tushadi.</i>"

    return Screen(
        text=(
            f"👑 <b>{role} TOPSHIRIG'I</b>\n"
            f"{'━' * 14}\n"
            f"🎫 <b>{display_number}</b>\n"
            f"⏰ Muddat: <b>{_fmt_dt(deadline_at)}</b>"
            f"{chosen_line}\n\n"
            "👥 <b>Mas'ul xodimlarni tanlang</b>\n"
            "<i>Birinchi tanlangan xodim ⭐ mas'ul bo'ladi. Har biriga Telegram orqali "
            "darhol xabar boradi. Bekor qilish uchun ismni qayta bosing.</i>"
        ),
        keyboard=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def build_directive_sent_screen(
    display_number: str,
    role: str,
    deadline_at: datetime | None,
    assignee_names: list[str],
    rid: int,
) -> Screen:
    """The receipt for a directive. Says what was actually promised, and to whom."""
    who = (
        "\n".join(
            f"{'⭐' if index == 0 else '•'} {esc(name)}"
            for index, name in enumerate(assignee_names)
        )
        if assignee_names
        else "<i>Tayinlanmadi — xodimlar guruhdan o'zlari oladi.</i>"
    )
    return Screen(
        text=(
            f"✅ <b>Topshiriq yuborildi!</b>\n"
            f"{'━' * 14}\n"
            f"🎫 <b>{display_number}</b> · <b>{role}</b>\n"
            f"⏰ Muddat: <b>{_fmt_dt(deadline_at)}</b>\n\n"
            f"🛠 <b>Tayinlangan xodimlar:</b>\n{who}\n\n"
            "RTM guruhiga alohida topshiriq kartochkasi tushdi."
        ),
        keyboard=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📋 Topshiriqni ochish", callback_data=ReqCB(act="open", rid=rid).pack()
                    )
                ],
                [menu_button()],
            ]
        ),
    )


def build_submitted_screen(display_number: str, summary: str, rid: int) -> Screen:
    extra = f"\nBiriktirilgan: {summary}" if summary else ""
    return Screen(
        text=(
            f"✅ <b>Murojaatingiz qabul qilindi!</b>\n\n"
            f"Raqami: <b>{display_number}</b>{extra}\n\n"
            "RTM xodimlari tez orada ko'rib chiqadi. "
            "Holatini «Mening murojaatlarim» dan kuzatib borishingiz mumkin."
        ),
        keyboard=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📋 Murojaatni ochish", callback_data=ReqCB(act="open", rid=rid).pack()
                    )
                ],
                [menu_button()],
            ]
        ),
    )
