"""Inventory screens inside the bot.

Two flows live here, and both are optional detours off the completion path:

* **Ishlatilgan inventar** — what the job consumed. Offered after the report, never before,
  and always with "Yo'q" as the one-tap way out. Most jobs consume nothing, so the default
  path has to be a single press or people will stop writing reports at all.
* **Kutish** — the job is blocked on a part nobody has. Parks the request with a date, which
  is what turns "we are waiting" into something the reporter can plan around.
"""

from afu_shared.models import InventoryCategory, InventoryItem
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.callbacks import AsgCB, InvCB
from app.ui.anchor import Screen

#: Items per page in the picker. Eight rows still fit a phone without scrolling past the
#: buttons that end the flow.
PAGE_SIZE = 8

#: Quantity shortcuts. Anything above this is typed — a keypad of twenty buttons is slower
#: to read than a two-character message.
QUICK_QUANTITIES = (1, 2, 3, 5)

#: How long a blocked request can be parked for. Concrete options rather than a free-text
#: date: every one of these is a normal supply answer, and a picker cannot be mistyped.
WAIT_OPTIONS = ((1, "1 kun"), (3, "3 kun"), (7, "1 hafta"), (14, "2 hafta"), (30, "1 oy"))


def _cancel_row(rid: int) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text="⬅️ Topshiriqqa qaytish", callback_data=AsgCB(act="open", rid=rid).pack()
        )
    ]


def build_use_prompt(rid: int, display_number: str, picks: list[tuple[str, int, str]]) -> Screen:
    """The hub of the completion flow: what has been picked, and the two ways out.

    Returned to after every pick, so the staffer always sees the running list rather than
    having to remember what they already added.
    """
    lines = [
        f"🔧 <b>{display_number}</b> — ishlatilgan inventar",
        "",
    ]
    if picks:
        lines.append("<b>Tanlangan:</b>")
        for name, quantity, unit in picks:
            lines.append(f"• {name} — <b>{quantity}</b> {unit}")
        lines.append("")
        lines.append("Yana qo'shasizmi yoki yakunlaymizmi?")
    else:
        lines.append("Bu ishda biror inventar ishlatildimi?")
        lines.append("")
        lines.append("<i>Ishlatilmagan bo'lsa — «Yo'q, yakunlash» ni bosing.</i>")

    rows = [
        [
            InlineKeyboardButton(
                text="➕ Yana qo'shish" if picks else "🔧 Ha, tanlash",
                callback_data=InvCB(act="cats", rid=rid).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text="✅ Yakunlash" if picks else "✅ Yo'q, yakunlash",
                callback_data=InvCB(act="done", rid=rid).pack(),
            )
        ],
    ]
    return Screen(text="\n".join(lines), keyboard=InlineKeyboardMarkup(inline_keyboard=rows))


def build_category_screen(
    rid: int, categories: list[tuple[InventoryCategory, int]], *, for_waiting: bool = False
) -> Screen:
    """Categories, each showing how many items are actually on the shelf.

    The count is the point: offering a category that turns out to be empty spends the one
    interaction the staffer had time for and teaches them not to bother next time.
    """
    rows = [
        [
            InlineKeyboardButton(
                text=f"{category.label_uz} · {count}"
                if count
                else f"{category.label_uz} · —",
                callback_data=InvCB(act="items", rid=rid, slug=category.slug).pack(),
            )
        ]
        for category, count in categories
        # An empty category is still shown when parking a request: the whole reason to
        # park is that the thing is not there.
        if count or for_waiting
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Orqaga", callback_data=InvCB(act="skip", rid=rid).pack()
            )
        ]
    )

    return Screen(
        text=(
            "📦 <b>Kategoriyani tanlang</b>\n\n"
            "<i>Yonidagi raqam — omborda mavjud turlar soni.</i>"
        ),
        keyboard=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def build_item_screen(
    rid: int,
    category: InventoryCategory,
    items: list[InventoryItem],
    page: int,
    total_pages: int,
) -> Screen:
    if not items:
        return Screen(
            text=(
                f"📦 <b>{category.label_uz}</b>\n\n"
                "Bu kategoriyada omborda hech narsa yo'q.\n\n"
                "<i>Kerakli qism yo'q bo'lsa, topshiriqni «⏸ Inventar kutish» "
                "holatiga o'tkazing.</i>"
            ),
            keyboard=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅️ Kategoriyalar",
                            callback_data=InvCB(act="cats", rid=rid).pack(),
                        )
                    ]
                ]
            ),
        )

    rows = [
        [
            InlineKeyboardButton(
                text=f"{item.name} · {item.quantity} {item.unit}",
                callback_data=InvCB(act="pick", rid=rid, iid=item.id, slug=category.slug).pack(),
            )
        ]
        for item in items
    ]

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 1:
            nav.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=InvCB(
                        act="items", rid=rid, slug=category.slug, page=page - 1
                    ).pack(),
                )
            )
        nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=InvCB(
                        act="items", rid=rid, slug=category.slug, page=page + 1
                    ).pack(),
                )
            )
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Kategoriyalar", callback_data=InvCB(act="cats", rid=rid).pack()
            )
        ]
    )
    return Screen(
        text=f"📦 <b>{category.label_uz}</b>\n\nQaysi qism ishlatildi?",
        keyboard=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def build_quantity_screen(rid: int, item: InventoryItem) -> Screen:
    """Shortcut buttons for the answers that are almost always right, and a way to type
    anything else. Offers no number larger than what is actually on the shelf."""
    available = [q for q in QUICK_QUANTITIES if q <= item.quantity]
    rows = [
        [
            InlineKeyboardButton(
                text=str(quantity),
                callback_data=InvCB(act="qty", rid=rid, iid=item.id, n=quantity).pack(),
            )
            for quantity in available
        ]
    ] if available else []

    rows.append(
        [
            InlineKeyboardButton(
                text="✏️ Boshqa son",
                callback_data=InvCB(act="qty", rid=rid, iid=item.id, n=0).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Orqaga",
                callback_data=InvCB(act="items", rid=rid, slug=item.category_slug).pack(),
            )
        ]
    )

    return Screen(
        text=(
            f"🔢 <b>{item.name}</b>\n"
            f"Omborda: <b>{item.quantity}</b> {item.unit}\n\n"
            "Nechta ishlatildi?"
        ),
        keyboard=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def build_wait_screen(rid: int, display_number: str) -> Screen:
    rows = [
        [
            InlineKeyboardButton(
                text=label, callback_data=InvCB(act="wait_for", rid=rid, n=days).pack()
            )
        ]
        for days, label in WAIT_OPTIONS
    ]
    rows.append(_cancel_row(rid))

    return Screen(
        text=(
            f"⏸ <b>{display_number}</b> — kutish holatiga o'tkazish\n\n"
            "Kerakli qism omborda yo'q bo'lsa, topshiriqni kutish holatiga qo'ying.\n"
            "Murojaatchiga bu haqda xabar boradi.\n\n"
            "<b>Qancha muddatga?</b>"
        ),
        keyboard=InlineKeyboardMarkup(inline_keyboard=rows),
    )
