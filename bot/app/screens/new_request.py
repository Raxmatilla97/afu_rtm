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
            "Endi muammoni qisqacha yozib yuboring.\n"
            "<i>Masalan: 3-qavat 305-xonadagi printer qog'oz tortmayapti.</i>"
        ),
        keyboard=InlineKeyboardMarkup(inline_keyboard=[CANCEL_ROW]),
    )


def build_attachment_choice_screen(category_label: str, description: str) -> Screen:
    return Screen(
        text=(
            f"🆕 <b>Yangi murojaat</b>\nTuri: {category_label}\n\n"
            f"<b>Tavsif:</b>\n{description}\n\n"
            "Rasm biriktirasizmi?"
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


def build_photo_screen(display_number: str, photo_count: int) -> Screen:
    counter = f"\n\nQabul qilindi: {photo_count} ta rasm" if photo_count else ""
    return Screen(
        text=(
            f"📎 <b>{display_number}</b>{counter}\n\n"
            "Rasmlarni yuboring. Tugagach «Tayyor» ni bosing."
        ),
        keyboard=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Tayyor", callback_data=FlowCB(act="photos_done").pack())]
            ]
        ),
    )


def build_submitted_screen(display_number: str, photo_count: int, rid: int) -> Screen:
    extra = f"\nBiriktirilgan fayllar: {photo_count} ta" if photo_count else ""
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
