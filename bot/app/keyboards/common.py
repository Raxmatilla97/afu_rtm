"""Reply keyboards and the shared inline building blocks.

Navigation lives on inline keyboards attached to the anchor message (see ``app/ui/anchor.py``);
the only reply keyboard left is the contact request, because ``request_contact`` has no
inline equivalent.
"""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from afu_shared.labels import BTN_SHARE_CONTACT
from app.callbacks import Nav


def contact_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SHARE_CONTACT, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def hemis_login_keyboard(login_url: str) -> InlineKeyboardMarkup:
    """The HEMIS login button.

    ``web_app`` opens the flow inside Telegram's webview and requires an HTTPS URL, which
    the production domain provides. If a client ever refuses to open it, swapping
    ``web_app=WebAppInfo(url=...)`` for ``url=...`` falls back to the system browser.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔐 HEMIS orqali kirish", web_app=WebAppInfo(url=login_url))]
        ]
    )


def back_button(to: str, page: int = 1, text: str = "⬅️ Orqaga") -> InlineKeyboardButton:
    """Back navigation names its parent explicitly — there is no history stack, so a button
    tapped long after it was rendered still leads somewhere sensible."""
    return InlineKeyboardButton(text=text, callback_data=Nav(to=to, page=page).pack())


def menu_button(text: str = "🏠 Bosh menyu") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=Nav(to="menu").pack())
