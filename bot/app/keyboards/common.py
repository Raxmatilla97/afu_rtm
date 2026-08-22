from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

BTN_NEW_REQUEST = "🆕 Yangi murojaat"
BTN_MY_REQUESTS = "📋 Mening murojaatlarim"
BTN_STATS = "📊 Statistika"
BTN_MY_ASSIGNMENTS = "🛠 Mening topshiriqlarim"


def main_menu_keyboard(*, is_rtm_staff: bool) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=BTN_NEW_REQUEST)], [KeyboardButton(text=BTN_MY_REQUESTS)]]
    if is_rtm_staff:
        rows.append([KeyboardButton(text=BTN_MY_ASSIGNMENTS)])
    rows.append([KeyboardButton(text=BTN_STATS)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def identity_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, bu men", callback_data="identity_confirm_yes"),
                InlineKeyboardButton(text="❌ Yo'q", callback_data="identity_confirm_no"),
            ]
        ]
    )


def contact_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni ulashish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
