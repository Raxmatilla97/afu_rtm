"""Inventory inside the completion flow, and parking a blocked request.

Both are detours a staff member takes *after* writing their report, and both are optional.
The picks are held in FSM state and only written to the database when the request is
actually closed — an abandoned flow must not silently consume stock, and a half-finished
completion is far easier to recover from than a shelf whose count is wrong.
"""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.assignments import OPEN_FOR_PICKUP, is_assigned
from afu_shared.enums import RequestStatus
from afu_shared.inventory import (
    NotEnoughStock,
    categories_with_stock,
    consume_for_request,
    items_in_category,
)
from afu_shared.models import Employee, InventoryCategory, InventoryItem, Request, RequestStatusHistory
from afu_shared.telegram_text import esc
from app.callbacks import InvCB
from app.screens import assignments as assignment_screens
from app.screens import inventory as screens
from app.states.inventory import InventoryStates
from app.states.staff_actions import StaffActionStates
from app.ui.anchor import render
from app.utils.transient import send_transient

logger = logging.getLogger(__name__)

router = Router(name="inventory")


async def _picks(state: FSMContext) -> list[dict]:
    return (await state.get_data()).get("picks", [])


async def _pick_rows(session: AsyncSession, picks: list[dict]) -> list[tuple[str, int, str]]:
    """Turn the stored ids back into something readable for the summary screen."""
    rows = []
    for pick in picks:
        item = await session.get(InventoryItem, pick["iid"])
        if item is not None:
            rows.append((item.name, pick["qty"], item.unit))
    return rows


async def _show_hub(
    callback_or_message,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
    redis: Redis,
    rid: int,
) -> None:
    request = await session.get(Request, rid)
    if request is None:
        return
    chat_id = (
        callback_or_message.message.chat.id
        if isinstance(callback_or_message, CallbackQuery)
        else callback_or_message.chat.id
    )
    await render(
        bot, redis, chat_id,
        screens.build_use_prompt(
            rid, request.display_number, await _pick_rows(session, await _picks(state))
        ),
    )


@router.callback_query(InvCB.filter(F.act == "skip"))
async def back_to_hub(
    callback: CallbackQuery,
    callback_data: InvCB,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await _show_hub(callback, session, state, bot, redis, callback_data.rid)


@router.callback_query(InvCB.filter(F.act == "cats"))
async def show_categories(
    callback: CallbackQuery,
    callback_data: InvCB,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    if not employee.is_rtm_staff:
        return

    categories = await categories_with_stock(session)
    if not any(count for _, count in categories):
        await callback.answer(
            "Omborda hech narsa yo'q. Topshiriqni «⏸ Inventar kutish» holatiga o'tkazing.",
            show_alert=True,
        )
        return

    await render(
        bot, redis, callback.message.chat.id,
        screens.build_category_screen(callback_data.rid, categories),
    )


@router.callback_query(InvCB.filter(F.act == "items"))
async def show_items(
    callback: CallbackQuery,
    callback_data: InvCB,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    category = await session.get(InventoryCategory, callback_data.slug)
    if category is None:
        return

    items = await items_in_category(session, category.slug)
    total_pages = max(1, (len(items) + screens.PAGE_SIZE - 1) // screens.PAGE_SIZE)
    page = min(max(1, callback_data.page), total_pages)
    start = (page - 1) * screens.PAGE_SIZE

    await render(
        bot, redis, callback.message.chat.id,
        screens.build_item_screen(
            callback_data.rid,
            category,
            items[start : start + screens.PAGE_SIZE],
            page,
            total_pages,
        ),
    )


@router.callback_query(InvCB.filter(F.act == "pick"))
async def pick_item(
    callback: CallbackQuery,
    callback_data: InvCB,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    item = await session.get(InventoryItem, callback_data.iid)
    if item is None:
        await callback.answer("Bu qism topilmadi.", show_alert=True)
        return

    await render(
        bot, redis, callback.message.chat.id,
        screens.build_quantity_screen(callback_data.rid, item),
    )


@router.callback_query(InvCB.filter(F.act == "qty"))
async def set_quantity(
    callback: CallbackQuery,
    callback_data: InvCB,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    item = await session.get(InventoryItem, callback_data.iid)
    if item is None:
        return

    if callback_data.n == 0:
        # "Boshqa son" — the one answer a picker cannot cover.
        await state.set_state(InventoryStates.awaiting_quantity)
        await state.update_data(pending_iid=item.id, rid=callback_data.rid)
        await send_transient(
            bot, redis, arq_pool, callback.message.chat.id,
            f"🔢 <b>{esc(item.name)}</b> — nechta ishlatildi? Raqam yozing "
            f"(omborda {item.quantity} {item.unit}).",
            ttl=120,
        )
        return

    await _add_pick(state, item, callback_data.n)
    await _show_hub(callback, session, state, bot, redis, callback_data.rid)


@router.message(InventoryStates.awaiting_quantity, F.text)
async def typed_quantity(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    data = await state.get_data()
    item = await session.get(InventoryItem, data.get("pending_iid", 0))
    rid = data.get("rid", 0)
    if item is None:
        await state.set_state(None)
        return

    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await send_transient(
            bot, redis, arq_pool, message.chat.id, "Faqat musbat raqam yozing, masalan: 2"
        )
        return

    quantity = int(raw)
    if quantity > item.quantity:
        await send_transient(
            bot, redis, arq_pool, message.chat.id,
            f"Omborda faqat {item.quantity} {item.unit} bor.",
        )
        return

    await _add_pick(state, item, quantity)
    # Back to the completion hub, not to no state at all: the hub is where "Yakunlash"
    # lives, and clearing the state would strand the report that is already written.
    await state.set_state(StaffActionStates.choosing_inventory)
    await _show_hub(message, session, state, bot, redis, rid)


async def _add_pick(state: FSMContext, item: InventoryItem, quantity: int) -> None:
    """Accumulate in state, never in the database.

    Nothing is deducted until the request is actually closed: a staffer who walks away
    mid-flow must not leave the shelf counting parts that were never used.
    """
    picks = (await state.get_data()).get("picks", [])
    for pick in picks:
        if pick["iid"] == item.id:
            pick["qty"] += quantity
            break
    else:
        picks.append({"iid": item.id, "qty": quantity})
    await state.update_data(picks=picks)


async def apply_picks(
    session: AsyncSession, state: FSMContext, request: Request, employee: Employee
) -> list[str]:
    """Deduct everything the staffer picked. Returns readable lines for the notifications.

    Called from the completion handler inside its transaction, so stock and status move
    together or not at all.
    """
    lines: list[str] = []
    for pick in await _picks(state):
        item = await session.get(InventoryItem, pick["iid"])
        if item is None:
            continue
        try:
            await consume_for_request(
                session, item, pick["qty"],
                request_id=request.id,
                employee_id=employee.id,
            )
        except NotEnoughStock:
            # Somebody else took the last one between the pick and the press. Recording a
            # smaller number would be a lie; skipping it and saying so is honest.
            logger.warning(
                "Request %s: not enough %s left to record %s", request.id, item.name, pick["qty"]
            )
            continue
        lines.append(f"{esc(item.name)} — {pick['qty']} {item.unit}")
    return lines


# --------------------------------------------------------------------------------------
# Parking a request that is blocked on a part


@router.callback_query(InvCB.filter(F.act == "wait"))
async def ask_wait_duration(
    callback: CallbackQuery,
    callback_data: InvCB,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    request = await session.get(Request, callback_data.rid)
    if request is None or not await is_assigned(session, request.id, employee.id):
        await callback.answer("Topshiriq topilmadi.", show_alert=True)
        return
    # Nothing to park: a returned or finished request is out of the queue already, and the
    # button only survives on a screen drawn before it left.
    if request.status not in OPEN_FOR_PICKUP:
        await callback.answer(
            "Bu murojaat yopilgan yoki qaytarib yuborilgan.", show_alert=True
        )
        return

    await state.set_state(None)
    await render(
        bot, redis, callback.message.chat.id,
        screens.build_wait_screen(request.id, request.display_number),
    )


@router.callback_query(InvCB.filter(F.act == "wait_for"))
async def start_waiting(
    callback: CallbackQuery,
    callback_data: InvCB,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    request = await session.get(Request, callback_data.rid)
    if request is None or not await is_assigned(session, request.id, employee.id):
        await callback.answer("Topshiriq topilmadi.", show_alert=True)
        return

    await state.set_state(InventoryStates.awaiting_wait_reason)
    await state.update_data(rid=request.id, wait_days=callback_data.n)
    await send_transient(
        bot, redis, arq_pool, callback.message.chat.id,
        "✍️ Nima kutilmoqda? Qisqacha yozing — bu matn murojaatchiga ham boradi.\n"
        "<i>Masalan: HP 85A toner buyurtma qilindi.</i>",
        ttl=180,
    )


@router.message(InventoryStates.awaiting_wait_reason, F.text)
async def park_request(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    data = await state.get_data()
    request = await session.get(Request, data.get("rid", 0))
    if request is None:
        await state.clear()
        return
    # Typing the reason takes a minute, and a supervisor can return the request inside it.
    if request.status not in OPEN_FOR_PICKUP:
        await state.clear()
        await message.answer("Bu murojaat qaytarib yuborilgan yoki yopilgan.")
        return

    days = int(data.get("wait_days", 3))
    reason = (message.text or "").strip() or "Kerakli qism kutilmoqda"

    previous = request.status
    request.status = RequestStatus.WAITING.value
    request.waiting_until = datetime.now(timezone.utc) + timedelta(days=days)
    request.waiting_reason = reason
    # The clock stops: the delay now belongs to the supply chain, and re-warning the
    # assignee about a deadline they cannot meet would be noise.
    request.overdue_notified_at = None
    session.add(
        RequestStatusHistory(
            request_id=request.id,
            from_status=previous,
            to_status=request.status,
            changed_by_employee_id=employee.id,
            note=f"{days} kun kutish: {reason}",
        )
    )
    await session.flush()
    await state.clear()
    await session.commit()

    await arq_pool.enqueue_job("notify_request_waiting", request.id, employee.id)
    await arq_pool.enqueue_job(
        "refresh_request_cards",
        request.id,
        f"⏸ <b>{request.display_number}</b> kutish holatiga o'tdi — {reason} "
        f"({days} kun).",
    )

    screen = await assignment_screens.build_detail(session, employee, request.id, 1)
    if screen:
        await render(bot, redis, message.chat.id, screen, force_new=True)
    await send_transient(
        bot, redis, arq_pool, message.chat.id,
        f"⏸ {request.display_number} kutish holatiga o'tkazildi. Murojaatchiga xabar berildi.",
    )
