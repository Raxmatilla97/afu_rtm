"""Pagination helpers for list screens."""

from collections.abc import Callable

from aiogram.types import InlineKeyboardButton

PAGE_SIZE = 5


def total_pages(total: int) -> int:
    return max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)


def offset_for(page: int) -> int:
    return (max(1, page) - 1) * PAGE_SIZE


def paging_row(
    page: int, pages: int, make_cb: Callable[[int], str]
) -> list[InlineKeyboardButton]:
    """A [⬅️] [2/5] [➡️] row. Returns empty for a single page.

    Arrows are omitted rather than disabled at the boundaries — Telegram has no disabled
    state, and a button that does nothing reads as broken.
    """
    if pages <= 1:
        return []

    row: list[InlineKeyboardButton] = []
    if page > 1:
        row.append(InlineKeyboardButton(text="⬅️", callback_data=make_cb(page - 1)))
    row.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="noop"))
    if page < pages:
        row.append(InlineKeyboardButton(text="➡️", callback_data=make_cb(page + 1)))
    return row
