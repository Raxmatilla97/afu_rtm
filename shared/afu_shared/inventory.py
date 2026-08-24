"""Stock changes.

The single owner of ``inventory_items.quantity``. Every change is recorded as a movement
and the quantity is updated in the same transaction, so the number on the item is always
the sum of its history. Nothing else should assign to ``quantity`` — a register you can
edit directly answers "how many now?" and no other question, and the one people actually
ask about consumables is where they went.
"""

import logging
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import InventoryStatus, MovementReason
from afu_shared.models import InventoryCategory, InventoryItem, InventoryMovement

logger = logging.getLogger(__name__)


class NotEnoughStock(Exception):
    """Raised when a consumption would take an item below zero.

    Refused rather than clamped: a negative or silently-truncated stock level is how a
    register stops being trusted, and "we thought we had three" is exactly the situation
    the waiting flow exists to handle.
    """

    def __init__(self, item: InventoryItem, requested: int) -> None:
        super().__init__(f"{item.name}: {requested} requested, {item.quantity} available")
        self.item = item
        self.requested = requested


async def record_movement(
    session: AsyncSession,
    item: InventoryItem,
    *,
    delta: int,
    reason: MovementReason,
    request_id: int | None = None,
    employee_id: int | None = None,
    user_id: int | None = None,
    unit_price: Decimal | None = None,
    note: str | None = None,
) -> InventoryMovement:
    """Move stock and write the row that explains it.

    ``delta`` is signed. Consumption passes a negative number; the caller decides the sign
    so this function never has to guess what a reason means.
    """
    if delta == 0:
        raise ValueError("A movement of zero explains nothing; refuse it rather than store it.")

    if delta < 0 and item.quantity + delta < 0:
        raise NotEnoughStock(item, abs(delta))

    movement = InventoryMovement(
        item_id=item.id,
        delta=delta,
        reason=reason.value,
        request_id=request_id,
        employee_id=employee_id,
        user_id=user_id,
        unit_price=unit_price if unit_price is not None else item.unit_price,
        note=note,
    )
    session.add(movement)
    item.quantity += delta

    # A purchase is also the best available evidence of what the thing currently costs.
    if reason is MovementReason.PURCHASE and unit_price is not None:
        item.unit_price = unit_price
    # Stock arriving is what turns a planned or ordered line into a real one.
    if delta > 0 and item.status in (
        InventoryStatus.PLANNED.value,
        InventoryStatus.ORDERED.value,
    ):
        item.status = InventoryStatus.AVAILABLE.value

    await session.flush()
    logger.info(
        "Inventory %s: %s%s %s (%s)", item.id, "+" if delta > 0 else "", delta, item.name, reason.value
    )
    return movement


async def consume_for_request(
    session: AsyncSession,
    item: InventoryItem,
    quantity: int,
    *,
    request_id: int,
    employee_id: int,
    note: str | None = None,
) -> InventoryMovement:
    """Take ``quantity`` off the shelf on behalf of a request."""
    if quantity <= 0:
        raise ValueError("Consumption must be positive")
    return await record_movement(
        session,
        item,
        delta=-quantity,
        reason=MovementReason.CONSUMPTION,
        request_id=request_id,
        employee_id=employee_id,
        note=note,
    )


async def active_categories(session: AsyncSession) -> list[InventoryCategory]:
    return list(
        (
            await session.execute(
                select(InventoryCategory)
                .where(InventoryCategory.is_active.is_(True))
                .order_by(InventoryCategory.sort_order, InventoryCategory.label_uz)
            )
        ).scalars()
    )


async def categories_with_stock(session: AsyncSession) -> list[tuple[InventoryCategory, int]]:
    """Active categories and how many *in-stock* items each holds.

    The count is what makes the bot's category step honest: offering "Toner" to somebody
    who is about to discover it is empty wastes the one interaction they had time for.
    """
    counts = dict(
        (
            await session.execute(
                select(InventoryItem.category_slug, func.count())
                .where(
                    InventoryItem.quantity > 0,
                    InventoryItem.status == InventoryStatus.AVAILABLE.value,
                )
                .group_by(InventoryItem.category_slug)
            )
        ).all()
    )
    return [(c, counts.get(c.slug, 0)) for c in await active_categories(session)]


async def items_in_category(
    session: AsyncSession, category_slug: str, *, only_in_stock: bool = True
) -> list[InventoryItem]:
    stmt = select(InventoryItem).where(InventoryItem.category_slug == category_slug)
    if only_in_stock:
        stmt = stmt.where(
            InventoryItem.quantity > 0,
            InventoryItem.status == InventoryStatus.AVAILABLE.value,
        )
    else:
        stmt = stmt.where(InventoryItem.status != InventoryStatus.ARCHIVED.value)
    return list((await session.execute(stmt.order_by(InventoryItem.name))).scalars())


async def used_on_request(session: AsyncSession, request_id: int) -> list[InventoryMovement]:
    """What a request consumed, newest last."""
    return list(
        (
            await session.execute(
                select(InventoryMovement)
                .where(
                    InventoryMovement.request_id == request_id,
                    InventoryMovement.reason == MovementReason.CONSUMPTION.value,
                )
                .order_by(InventoryMovement.id)
            )
        ).scalars()
    )


async def low_stock_items(session: AsyncSession) -> list[InventoryItem]:
    """Items at or below their reorder threshold, scarcest first."""
    return list(
        (
            await session.execute(
                select(InventoryItem)
                .where(
                    InventoryItem.min_quantity > 0,
                    InventoryItem.quantity <= InventoryItem.min_quantity,
                    InventoryItem.status != InventoryStatus.ARCHIVED.value,
                )
                .order_by(InventoryItem.quantity, InventoryItem.name)
            )
        ).scalars()
    )
