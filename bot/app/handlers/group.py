"""The RTM group chat: registration, and the buttons on request cards.

Everything here runs in a group, which makes it the opposite of the rest of the bot. There
is no anchor screen and no conversation state — a group is shared, so the bot owns exactly
one message per request and answers everything else with a pop-up that only the person who
pressed sees. Anything needing typed input sends the user to their own chat with the bot.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import (
    JOIN_TRANSITION,
    LEAVE_TRANSITION,
    ChatMemberUpdatedFilter,
    Command,
)
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message
from arq import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.assignments import OPEN_FOR_PICKUP, add_assignee, assignees_of
from afu_shared.group_card import PICKER_PAGE_SIZE, build_picker_keyboard
from afu_shared.models import Employee, NotificationChat, Request
from app.callbacks import GrpCB

logger = logging.getLogger(__name__)

router = Router(name="group")

#: Plain strings, not the enum members. ``ChatType`` is a ``str, Enum``, whose members hash
#: by name rather than by value — so ``"group" in {ChatType.GROUP}`` is False and a set of
#: enum members would match nothing at all. Telegram sends us the value.
GROUP_TYPES = {ChatType.GROUP.value, ChatType.SUPERGROUP.value}

# Groups only. The private-chat flows are registered on their own routers and must never
# see these handlers, nor these handlers them.
router.message.filter(F.chat.type.in_(GROUP_TYPES))
router.callback_query.filter(F.message.chat.type.in_(GROUP_TYPES))

WELCOME = (
    "👋 <b>RTM Murojaatlar boti ulandi</b>\n\n"
    "Endi bu guruhga yangi murojaatlar tushadi. Har bir murojaat bitta kartochka "
    "ko'rinishida chiqadi va holati o'zgargani sayin o'sha kartochka yangilanib boradi.\n\n"
    "✋ <b>Men bajaraman</b> — murojaatni o'z zimmangizga olasiz\n"
    "🤝 Bir murojaatni bir necha xodim birgalikda olishi mumkin\n"
    "💬 <b>Botda ochish</b> — yozishmalar, hisobot va yakunlash shaxsiy chatda\n\n"
    "<i>O'chirish uchun: /rtm_off</i>"
)

NOT_AUTHORIZED = (
    "🔒 <b>Ulanmadi</b>\n\n"
    "Bu guruhni faqat <b>RTM xodimi</b> ulay oladi. Botga shaxsan kirib "
    "ro'yxatdan o'tgan RTM xodimi shu yerda <code>/rtm_on</code> buyrug'ini yuborsa, "
    "guruh ulanadi."
)

#: Shown as a pop-up, so it never lands in the group chat.
NOT_A_MANAGER = (
    "🔒 Bu tugma faqat Boshliq yoki Admin uchun.\n\n"
    "Murojaatni o'zingiz olmoqchi bo'lsangiz — «✋ Men bajaraman» tugmasini bosing."
)


def _is_rtm_staff(employee: Employee | None) -> bool:
    return employee is not None and employee.is_eligible and employee.is_rtm_staff


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def bot_added(
    event: ChatMemberUpdated,
    session: AsyncSession,
    employee: Employee | None,
    bot: Bot,
) -> None:
    """Register the group — but only when an RTM staff member is the one adding the bot.

    Without that check anyone could add this bot to any chat and start receiving every
    request in the university, complete with reporters' names and phone numbers.

    An unauthorised add leaves the bot sitting in the chat rather than making it walk out:
    leaving looks like a malfunction, and staying costs nothing because an unregistered chat
    is never posted to. A staff member can finish the job with /rtm_on.
    """
    if event.chat.type not in GROUP_TYPES:
        return

    if not _is_rtm_staff(employee):
        logger.info("Bot added to chat %s by a non-RTM user", event.chat.id)
        await bot.send_message(event.chat.id, NOT_AUTHORIZED, parse_mode="HTML")
        return

    await _activate(session, event.chat.id, event.chat.title, event.chat.type, employee)
    await bot.send_message(event.chat.id, WELCOME, parse_mode="HTML")


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=LEAVE_TRANSITION))
async def bot_removed(event: ChatMemberUpdated, session: AsyncSession) -> None:
    """Stop posting, but keep the row.

    The registration is deactivated rather than deleted so that re-adding the bot restores
    the group without losing which request cards already live there.
    """
    chat = await session.get(NotificationChat, event.chat.id)
    if chat is not None:
        chat.is_active = False
        logger.info("Bot removed from group %s", event.chat.id)


@router.message(Command("rtm_on"))
async def enable_group(
    message: Message, session: AsyncSession, employee: Employee | None
) -> None:
    if not _is_rtm_staff(employee):
        await message.reply(NOT_AUTHORIZED, parse_mode="HTML")
        return

    await _activate(session, message.chat.id, message.chat.title, message.chat.type, employee)
    await message.reply(WELCOME, parse_mode="HTML")


@router.message(Command("rtm_off"))
async def disable_group(
    message: Message, session: AsyncSession, employee: Employee | None
) -> None:
    if not _is_rtm_staff(employee):
        await message.reply(NOT_AUTHORIZED, parse_mode="HTML")
        return

    chat = await session.get(NotificationChat, message.chat.id)
    if chat is not None:
        chat.is_active = False
    await message.reply(
        "🔕 Bu guruhga endi murojaatlar yuborilmaydi. Qayta yoqish: <code>/rtm_on</code>",
        parse_mode="HTML",
    )


async def _activate(
    session: AsyncSession,
    chat_id: int,
    title: str | None,
    chat_type: str,
    employee: Employee,
) -> None:
    chat = await session.get(NotificationChat, chat_id)
    if chat is None:
        chat = NotificationChat(chat_id=chat_id)
        session.add(chat)
    chat.title = title
    chat.chat_type = str(chat_type)
    chat.is_active = True
    chat.left_at = None
    chat.registered_by_employee_id = employee.id
    await session.flush()
    logger.info("Group %s registered by employee %s", chat_id, employee.id)


@router.callback_query(GrpCB.filter(F.act == "take"))
async def take_request(
    callback: CallbackQuery,
    callback_data: GrpCB,
    session: AsyncSession,
    employee: Employee,
    arq_pool: ArqRedis,
) -> None:
    """Self-assignment from the group — the point of the whole card."""
    if not employee.is_rtm_staff:
        await callback.answer(
            "Bu tugma faqat RTM xodimlari uchun. Admin sizni RTM xodimi deb belgilashi kerak.",
            show_alert=True,
        )
        return

    request = await session.get(Request, callback_data.rid)
    if request is None:
        await callback.answer("Murojaat topilmadi.", show_alert=True)
        return
    if request.status not in OPEN_FOR_PICKUP:
        await callback.answer("Bu murojaat allaqachon yopilgan.", show_alert=True)
        return

    if not await add_assignee(session, request, employee):
        await callback.answer("Siz allaqachon bu murojaatni olgansiz. 👍", show_alert=True)
        return

    # Commit before queueing: the worker re-reads the request in its own session and would
    # otherwise redraw the card without this change on it.
    await session.commit()

    await callback.answer("✅ Murojaat sizga biriktirildi. Tafsilotlar botga yuborildi.")
    await arq_pool.enqueue_job(
        "refresh_request_cards",
        request.id,
        f"🙋 <b>{employee.full_name}</b> — <b>{request.display_number}</b> ni o'z zimmasiga oldi.",
    )
    # The full brief with every attachment goes to their own chat, where it can be read and
    # replayed without filling the group.
    await arq_pool.enqueue_job("notify_request_assigned", request.id, employee.id)


@router.callback_query(GrpCB.filter(F.act == "leave"))
async def leave_request(callback: CallbackQuery) -> None:
    """Kept only for cards printed before the button was removed.

    Giving a request back is no longer possible: taking one is a commitment made in front
    of the group, and a one-tap undo turns it into a guess. Only a supervisor can take
    somebody off a job, and they do it on the web where the change is recorded.
    """
    await callback.answer(
        "Olingan murojaatdan voz kechib bo'lmaydi. Zarur bo'lsa Boshliq yoki Admin "
        "veb-saytdan o'zgartiradi.",
        show_alert=True,
    )


@router.callback_query(GrpCB.filter(F.act == "assign"))
async def open_picker(
    callback: CallbackQuery,
    callback_data: GrpCB,
    session: AsyncSession,
    employee: Employee,
) -> None:
    """Show the RTM staff list on the card, for a supervisor or admin only.

    The button is on a shared message so everyone can see it; the permission check is here,
    and anybody else gets a pop-up that only they see. That is the whole reason the check
    is at press time rather than at draw time.
    """
    if not employee.can_manage_assignments:
        await callback.answer(NOT_A_MANAGER, show_alert=True)
        return
    if callback.message is None:
        await callback.answer()
        return

    request = await session.get(Request, callback_data.rid)
    if request is None:
        await callback.answer("Murojaat topilmadi.", show_alert=True)
        return

    staff = list(
        (
            await session.execute(
                select(Employee)
                .where(Employee.is_rtm_staff.is_(True), Employee.is_blocked.is_(False))
                .order_by(Employee.full_name)
            )
        ).scalars()
    )
    if not staff:
        await callback.answer("RTM xodimlari ro'yxati bo'sh.", show_alert=True)
        return

    total_pages = max(1, (len(staff) + PICKER_PAGE_SIZE - 1) // PICKER_PAGE_SIZE)
    page = min(max(1, callback_data.page), total_pages)
    start = (page - 1) * PICKER_PAGE_SIZE

    assigned = {row.employee_id for row in await assignees_of(session, request.id)}
    await callback.answer()
    await callback.message.edit_reply_markup(
        reply_markup=build_picker_keyboard(
            request.id, staff[start : start + PICKER_PAGE_SIZE], assigned, page, total_pages
        )
    )


@router.callback_query(GrpCB.filter(F.act == "pick"))
async def pick_assignee(
    callback: CallbackQuery,
    callback_data: GrpCB,
    session: AsyncSession,
    employee: Employee,
    arq_pool: ArqRedis,
) -> None:
    """Hand the request to the chosen staff member."""
    if not employee.can_manage_assignments:
        await callback.answer(NOT_A_MANAGER, show_alert=True)
        return

    request = await session.get(Request, callback_data.rid)
    if request is None:
        await callback.answer("Murojaat topilmadi.", show_alert=True)
        return
    if request.status not in OPEN_FOR_PICKUP:
        await callback.answer("Bu murojaat allaqachon yopilgan.", show_alert=True)
        return

    target = await session.get(Employee, callback_data.eid)
    if target is None or not target.is_rtm_staff or not target.is_eligible:
        await callback.answer("Bu xodimni tayinlab bo'lmaydi.", show_alert=True)
        return

    if not await add_assignee(session, request, target):
        await callback.answer(f"{target.full_name} allaqachon shu murojaatda.", show_alert=True)
        return

    # Commit before queueing: the worker redraws the card from its own read of the database.
    await session.commit()
    await callback.answer(f"✅ {target.full_name} tayinlandi.")

    await arq_pool.enqueue_job(
        "refresh_request_cards",
        request.id,
        f"📌 <b>{employee.full_name}</b> — <b>{request.display_number}</b> ni "
        f"<b>{target.full_name}</b> ga tayinladi.",
    )
    # The full brief with every attachment goes to the person who now has to do the work.
    await arq_pool.enqueue_job("notify_request_assigned", request.id, target.id)


@router.callback_query(GrpCB.filter(F.act == "back"))
async def close_picker(
    callback: CallbackQuery, callback_data: GrpCB, arq_pool: ArqRedis
) -> None:
    """Put the normal card buttons back.

    Routed through the refresher rather than rebuilt here so the card returns to exactly
    what the worker would draw — including anything that changed while the picker was open.
    """
    await callback.answer()
    await arq_pool.enqueue_job("refresh_request_cards", callback_data.rid)


@router.callback_query(GrpCB.filter(F.act == "files"))
async def show_files(
    callback: CallbackQuery,
    callback_data: GrpCB,
    session: AsyncSession,
    employee: Employee,
    arq_pool: ArqRedis,
) -> None:
    if not employee.is_rtm_staff:
        await callback.answer("Bu tugma faqat RTM xodimlari uchun.", show_alert=True)
        return
    if callback.message is None:
        await callback.answer()
        return

    await callback.answer("📎 Materiallar yuborilmoqda...")
    await arq_pool.enqueue_job(
        "send_request_files_to_chat", callback_data.rid, callback.message.chat.id
    )


@router.callback_query()
async def unknown_group_callback(callback: CallbackQuery) -> None:
    """Stops the spinner on a button from before a restart. Must stay last in this router."""
    await callback.answer()
