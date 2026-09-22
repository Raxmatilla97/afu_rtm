"""Main menu and help."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from afu_shared.models import Employee
from afu_shared.people import short_name
from afu_shared.telegram_text import esc
from app.callbacks import Nav, SoftCB
from app.keyboards.common import menu_button
from app.ui.anchor import Screen


def build_menu(employee: Employee) -> Screen:
    # Familiya + ism, like every card — see afu_shared.people.
    directive = employee.can_file_managed_request
    role = ("ADMIN" if employee.is_admin else "BOSHLIQ") if directive else None

    text = (
        f"👤 <b>{esc(short_name(employee.full_name))}</b>"
        f"{f' · <b>[{role}]</b>' if role else ''}\n"
        f"{esc(employee.department.name) if employee.department else 'Bo‘lim ko‘rsatilmagan'}\n\n"
        "Nima qilmoqchisiz?"
    )

    rows = [
        [
            InlineKeyboardButton(
                # Named for what it produces. A Boshliq pressing "Yangi murojaat" and
                # landing in a deadline picker would reasonably think they had mis-tapped.
                text="👑 Yangi topshiriq" if directive else "🆕 Yangi murojaat",
                callback_data=Nav(to="newreq").pack(),
            )
        ],
        [InlineKeyboardButton(text="📋 Mening murojaatlarim", callback_data=Nav(to="myreq").pack())],
    ]
    if employee.is_rtm_staff:
        rows.append(
            [InlineKeyboardButton(text="🛠 Mening topshiriqlarim", callback_data=Nav(to="assign").pack())]
        )
    rows.append([InlineKeyboardButton(text="📊 Statistika", callback_data=Nav(to="stats").pack())])
    rows.append([InlineKeyboardButton(text="❓ Yordam", callback_data=Nav(to="help").pack())])

    return Screen(text=text, keyboard=InlineKeyboardMarkup(inline_keyboard=rows))


def build_help(employee: Employee) -> Screen:
    lines = [
        "❓ <b>Yordam</b>\n",
        "<b>Murojaat yuborish</b>",
        "«🆕 Yangi murojaat» → kategoriyani tanlang → muammoni yozing → xohlasangiz rasm biriktiring.\n",
        "<b>Kuzatib borish</b>",
        "«📋 Mening murojaatlarim» dan murojaatni ochib, holatini ko'rasiz va "
        "RTM xodimi bilan yozishasiz. Bajarilgach, xizmatni baholay olasiz.\n",
    ]
    if employee.can_file_managed_request:
        lines += [
            "<b>Boshliq uchun — topshiriq berish</b>",
            "«👑 Yangi topshiriq» → kategoriya → tavsif → <b>bajarish muddati</b> "
            "(1 soat, 2 soat, 6 soat, 1 kun, 2 kun, 1 hafta) → <b>mas'ul xodimlar</b>.",
            "Birinchi tanlangan xodim mas'ul bo'ladi, har biriga darhol xabar boradi. "
            "RTM guruhiga oddiy murojaat emas, alohida topshiriq kartochkasi tushadi.\n",
        ]
    elif employee.is_admin:
        lines += [
            "<b>Nega menda muddat va bajaruvchi bandlari yo'q?</b>",
            "Sizda <b>Admin</b> roli bor, <b>Boshliq</b> roli yo'q. Topshiriq berish — "
            "muddat va mas'ul xodim belgilash — RTM boshlig'ining huquqi. "
            "Murojaatingiz oddiy tartibda navbatga tushadi.\n",
        ]

    if employee.is_rtm_staff:
        lines += [
            "<b>RTM xodimi uchun</b>",
            "«🛠 Mening topshiriqlarim» — sizga tayinlangan murojaatlar. "
            "Ishni boshlash, murojaatchiga yozish, ichki izoh qoldirish va yakunlash mumkin.\n",
        ]
    lines += [
        "<b>Soft va drayverlar</b>",
        "Printer drayveri, antivirus, ofis dasturlari — pastdagi tugmadan. "
        "Fayl shu chatga yuboriladi va 10 daqiqadan so'ng o'chadi.\n",
        "<b>Parolni unutdingizmi?</b>",
        "1. /chiqish yozing — hisobdan chiqasiz.",
        "2. «⚡ Tezkor kirish» ni bosing va xodim ID raqamingizni yuboring.",
        "3. Parolni noto'g'ri kiritsangiz, «🔑 Parolni tiklash» tugmasi chiqadi — bosing.",
        "4. Pochtangizga havola keladi; rtm.afu.uz saytida yangi parol o'rnatasiz.",
        "5. Botga qaytib, ID raqam va yangi parol bilan kiring.",
        "<i>Pochta biriktirmagan bo'lsangiz, parolni faqat RTM tiklab bera oladi.</i>\n",
        "<b>Buyruqlar</b>",
        "/menu — asosiy menyu",
        "/help — shu sahifa",
        "/cancel — joriy amalni bekor qilish",
        "/chiqish — hisobdan chiqish (boshqa ID bilan kirish uchun)",
    ]

    return Screen(
        text="\n".join(lines),
        keyboard=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💿 Soft va drayverlar",
                        callback_data=SoftCB(act="cats").pack(),
                    )
                ],
                [menu_button()],
            ]
        ),
    )
