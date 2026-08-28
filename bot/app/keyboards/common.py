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
)

from afu_shared.labels import BTN_SHARE_CONTACT
from app.callbacks import Nav, QuickCB


def contact_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SHARE_CONTACT, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def hemis_login_keyboard(login_url: str) -> InlineKeyboardMarkup:
    """The HEMIS login button — a plain URL button, deliberately NOT a Mini App.

    This used to be ``web_app=WebAppInfo(url=...)``, and that is what made the login
    unfinishable in practice. HEMIS hands the user off to One-ID and, on the way back,
    drops them on their HEMIS profile instead of returning to ``/oauth/authorize`` — so the
    login has to be re-entered once, now that a HEMIS session cookie exists. A Mini App
    webview throws its cookie jar away when it closes, so every retry started from zero and
    the user could loop forever. An ordinary browser keeps the session, so the second
    attempt walks straight through to our callback.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔐 HEMIS orqali kirish", url=login_url)]
        ]
    )


def login_options_keyboard(login_url: str) -> InlineKeyboardMarkup:
    """The two ways in, quickest first.

    HEMIS is second and labelled as the harder one because that is the truth: it now hands
    the user to One-ID, which most staff have never linked. Putting it first was sending
    everybody down the route that fails.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡ Tezkor kirish (tavsiya etiladi)",
                    callback_data=QuickCB(act="start").pack(),
                )
            ],
            [InlineKeyboardButton(text="🔐 HEMIS orqali kirish", url=login_url)],
        ]
    )


def quick_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Orqaga", callback_data=QuickCB(act="back").pack()
                )
            ]
        ]
    )


def quick_password_keyboard(*, offer_reset: bool) -> InlineKeyboardMarkup:
    """The password step. The reset button appears once a password has actually failed."""
    rows: list[list[InlineKeyboardButton]] = []
    if offer_reset:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔑 Parolni tiklash",
                    callback_data=QuickCB(act="reset").pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Orqaga", callback_data=QuickCB(act="back").pack()
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_button(to: str, page: int = 1, text: str = "⬅️ Orqaga") -> InlineKeyboardButton:
    """Back navigation names its parent explicitly — there is no history stack, so a button
    tapped long after it was rendered still leads somewhere sensible."""
    return InlineKeyboardButton(text=text, callback_data=Nav(to=to, page=page).pack())


def menu_button(text: str = "🏠 Bosh menyu") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=Nav(to="menu").pack())
