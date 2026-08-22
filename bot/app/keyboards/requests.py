from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from afu_shared.enums import RequestStatus
from afu_shared.models import Category, Request


def category_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=c.label_uz, callback_data=f"cat:{c.slug}")] for c in categories]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def attach_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📎 Ha, biriktiraman", callback_data="attach_yes"),
                InlineKeyboardButton(text="➡️ Yo'q", callback_data="attach_no"),
            ]
        ]
    )


def photo_done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Tayyor", callback_data="photos_done")]]
    )


def assignment_list_keyboard(requests: list[Request]) -> InlineKeyboardMarkup:
    rows = []
    for r in requests:
        deadline = r.deadline_at.strftime("%d.%m %H:%M") if r.deadline_at else "-"
        rows.append(
            [InlineKeyboardButton(text=f"{r.display_number} · {deadline}", callback_data=f"req:{r.id}")]
        )
    if not rows:
        rows = [[InlineKeyboardButton(text="Topshiriqlar yo'q", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def request_detail_keyboard(request: Request) -> InlineKeyboardMarkup:
    rows = []
    if request.status == RequestStatus.ASSIGNED.value:
        rows.append([InlineKeyboardButton(text="▶️ Ishga boshladim", callback_data=f"req_start:{request.id}")])
    if request.status in (RequestStatus.ASSIGNED.value, RequestStatus.IN_PROGRESS.value):
        rows.append([InlineKeyboardButton(text="✅ Bajarildi", callback_data=f"req_complete:{request.id}")])
        rows.append([InlineKeyboardButton(text="💬 Murojaatchiga xabar", callback_data=f"req_msg:{request.id}")])
        rows.append([InlineKeyboardButton(text="🗂 Ichki muhokama", callback_data=f"req_internal:{request.id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Ro'yxatga qaytish", callback_data="req_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
