"""RTM Soft: the driver and software shelf, as seen from the bot."""

from afu_shared.models import SoftAsset, SoftCategory
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.callbacks import Nav, SoftCB
from app.keyboards.common import menu_button
from app.ui.anchor import Screen

PAGE_SIZE = 8

INTRO = (
    "💿 <b>Soft va drayverlar</b>\n\n"
    "Kerakli dastur yoki drayverni kategoriyadan tanlang — fayl shu chatga yuboriladi.\n\n"
    "<i>🕙 Yuborilgan fayllar 10 daqiqadan so'ng avtomatik o'chiriladi. "
    "Kerak bo'lsa qaytadan yuklab oling.</i>"
)


def _human_size(size: int | None) -> str:
    if not size:
        return ""
    mb = size / (1024 * 1024)
    return f"{mb:.1f} MB" if mb >= 1 else f"{max(1, size // 1024)} KB"


def build_category_screen(categories: list[tuple[SoftCategory, int]]) -> Screen:
    """Categories, each with how many files it actually holds.

    Empty categories are hidden rather than shown greyed out: a shelf with nothing on it is
    not a choice, and offering it wastes the tap.
    """
    rows = [
        [
            InlineKeyboardButton(
                text=f"{category.label_uz} · {count}",
                callback_data=SoftCB(act="list", slug=category.slug).pack(),
            )
        ]
        for category, count in categories
        if count
    ]

    if not rows:
        return Screen(
            text=(
                "💿 <b>Soft va drayverlar</b>\n\n"
                "Hozircha bu yerda fayl yo'q.\n\n"
                "<i>Fayllarni RTM administratori veb-saytdan yuklaydi.</i>"
            ),
            keyboard=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❓ Yordam", callback_data=Nav(to="help").pack())], [menu_button()]]
            ),
        )

    rows.append(
        [
            InlineKeyboardButton(text="❓ Yordam", callback_data=Nav(to="help").pack()),
            menu_button(),
        ]
    )
    return Screen(text=INTRO, keyboard=InlineKeyboardMarkup(inline_keyboard=rows))


def build_asset_screen(
    category: SoftCategory, assets: list[SoftAsset], page: int, total_pages: int
) -> Screen:
    rows = [
        [
            InlineKeyboardButton(
                text=_asset_label(asset),
                callback_data=SoftCB(act="get", aid=asset.id, slug=category.slug).pack(),
            )
        ]
        for asset in assets
    ]

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 1:
            nav.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=SoftCB(act="list", slug=category.slug, page=page - 1).pack(),
                )
            )
        nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=SoftCB(act="list", slug=category.slug, page=page + 1).pack(),
                )
            )
        rows.append(nav)

    rows.append(
        [InlineKeyboardButton(text="⬅️ Kategoriyalar", callback_data=SoftCB(act="cats").pack())]
    )

    lines = [f"💿 <b>{category.label_uz}</b>", ""]
    for asset in assets:
        detail = " · ".join(
            part for part in (asset.version, _human_size(asset.file_size)) if part
        )
        lines.append(f"• <b>{asset.title}</b>" + (f"\n  <i>{detail}</i>" if detail else ""))
        if asset.description:
            lines.append(f"  {asset.description}")
    lines.append("\n<i>Yuklab olish uchun nomini bosing.</i>")

    return Screen(text="\n".join(lines), keyboard=InlineKeyboardMarkup(inline_keyboard=rows))


def _asset_label(asset: SoftAsset) -> str:
    size = _human_size(asset.file_size)
    label = asset.title if not asset.version else f"{asset.title} {asset.version}"
    return f"⬇️ {label}" + (f" ({size})" if size else "")
