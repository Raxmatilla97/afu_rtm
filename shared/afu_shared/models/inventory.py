"""RTM inventory: what is on the shelf, and where it went.

The design rule is that **stock is never edited directly**. Every change is a movement row,
and the quantity on the item is the running total those rows produce. That is what makes
"we bought 12 toners in March and have 3 left" answerable at all — an editable number tells
you the present and nothing else, and the question people actually ask about consumables is
where they went.

``afu_shared.inventory`` owns the writes; nothing else should touch ``quantity``.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.enums import InventoryStatus
from afu_shared.models.base import Base, TimestampMixin
from afu_shared.models.employee import Employee
from afu_shared.models.user import User

if TYPE_CHECKING:
    from afu_shared.models.request import Request


class InventoryCategory(Base):
    """Toner, kabel, ehtiyot qism… — the axis staff search along.

    A separate table from ``categories`` (which types *requests*) because the two lists
    have nothing to do with each other: a request about a printer may consume a toner, a
    cable and an hour of somebody's time.
    """

    __tablename__ = "inventory_categories"

    slug: Mapped[str] = mapped_column(String(40), primary_key=True)
    label_uz: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<InventoryCategory slug={self.slug!r}>"


class InventoryItem(TimestampMixin, Base):
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    category_slug: Mapped[str] = mapped_column(
        String(40), ForeignKey("inventory_categories.slug"), nullable=False, index=True
    )
    category: Mapped["InventoryCategory"] = relationship("InventoryCategory", lazy="selectin")

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: "dona", "litr", "metr" — printed next to every quantity so a number is never bare.
    unit: Mapped[str] = mapped_column(String(24), nullable=False, default="dona")

    #: The running total of every movement. Never assigned outside ``afu_shared.inventory``.
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Below this the item counts as low and is surfaced for reordering. 0 disables it.
    min_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=InventoryStatus.AVAILABLE.value, index=True
    )

    #: Optional throughout. Plenty of stock arrives without anyone recording what it cost,
    #: and refusing to track an item until somebody types a price would make the register
    #: useless for exactly the consumables it exists for.
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    movements: Mapped[list["InventoryMovement"]] = relationship(
        "InventoryMovement",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="InventoryMovement.id.desc()",
    )
    attachments: Mapped[list["InventoryAttachment"]] = relationship(
        "InventoryAttachment",
        back_populates="item",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="InventoryAttachment.id",
    )

    def __repr__(self) -> str:
        return f"<InventoryItem id={self.id} name={self.name!r} qty={self.quantity}>"

    @property
    def is_low(self) -> bool:
        return self.min_quantity > 0 and self.quantity <= self.min_quantity

    @property
    def in_stock(self) -> bool:
        return self.quantity > 0


class InventoryMovement(Base):
    """One change to one item's stock, with its reason attached.

    ``request_id`` is what ties a consumed part back to the job that consumed it, which is
    the question this whole subsystem exists to answer.
    """

    __tablename__ = "inventory_movements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("inventory_items.id"), nullable=False, index=True
    )
    # selectin: movements are read in async contexts (the bot screen, the API), where a
    # lazy load on attribute access raises instead of quietly issuing a query.
    item: Mapped["InventoryItem"] = relationship(
        "InventoryItem", back_populates="movements", lazy="selectin"
    )

    #: Signed: positive adds to stock, negative removes. Storing the sign rather than a
    #: separate direction column means the running total is a plain SUM.
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    request_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("requests.id"), nullable=True, index=True
    )
    request: Mapped["Request | None"] = relationship("Request")

    employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=True
    )
    employee: Mapped["Employee | None"] = relationship("Employee", lazy="selectin")
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    user: Mapped["User | None"] = relationship("User")

    #: What this batch actually cost, if anyone recorded it. Kept on the movement rather
    #: than only on the item because the price of a toner in March is not its price in
    #: October, and a purchase record that silently rewrites history is worse than none.
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    attachments: Mapped[list["InventoryAttachment"]] = relationship(
        "InventoryAttachment", back_populates="movement", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<InventoryMovement id={self.id} item={self.item_id} delta={self.delta}>"

    @property
    def total_price(self) -> Decimal | None:
        if self.unit_price is None:
            return None
        return self.unit_price * abs(self.delta)


class InventoryAttachment(Base):
    """A receipt, invoice or photo.

    Hangs off the movement when there is one — a receipt documents a purchase, not a
    concept — and off the item alone when the purchase has not happened yet, which is the
    "planned" case.
    """

    __tablename__ = "inventory_attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("inventory_items.id"), nullable=False, index=True
    )
    item: Mapped["InventoryItem"] = relationship("InventoryItem", back_populates="attachments")

    movement_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("inventory_movements.id"), nullable=True, index=True
    )
    movement: Mapped["InventoryMovement | None"] = relationship(
        "InventoryMovement", back_populates="attachments"
    )

    file_path: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    uploaded_by_employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<InventoryAttachment id={self.id} item={self.item_id}>"
