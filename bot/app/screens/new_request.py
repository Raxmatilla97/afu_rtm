"""New-request flow screens."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Category
from app.callbacks import CatCB, FlowCB, Nav, ReqCB
from app.keyboards.common import menu_button
from app.ui.anchor import Screen

CANCEL_ROW = [InlineKeyboardButton(text="✖️ Bekor qilish", callback_data=Nav(to="menu").pack())]


async def build_category_screen(session: AsyncSession) -> Screen:
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
    return Screen(
        text="🆕 <b>Yangi murojaat</b>\n\nMuammo turini tanlang:",
        keyboard=InlineKeyboardMarkup(inline_keyboard=rows),
    )


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
            f"<b>Tavsif:</b>\n{description}\n\n"
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
