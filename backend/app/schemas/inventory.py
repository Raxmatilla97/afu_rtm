from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from afu_shared.labels import inventory_status_label, movement_reason_label


class InventoryCategoryResponse(BaseModel):
    slug: str
    label_uz: str
    sort_order: int
    is_active: bool
    item_count: int = 0

    class Config:
        from_attributes = True


class InventoryAttachmentResponse(BaseModel):
    id: int
    item_id: int
    movement_id: int | None
    original_filename: str | None
    content_type: str | None
    file_size: int | None
    url: str
    created_at: datetime

    @classmethod
    def from_attachment(cls, a) -> "InventoryAttachmentResponse":
        return cls(
            id=a.id,
            item_id=a.item_id,
            movement_id=a.movement_id,
            original_filename=a.original_filename,
            content_type=a.content_type,
            file_size=a.file_size,
            url=f"/api/inventory/items/{a.item_id}/attachments/{a.id}",
            created_at=a.created_at,
        )


class InventoryItemCreate(BaseModel):
    category_slug: str
    name: str
    unit: str = "dona"
    min_quantity: int = 0
    #: Optional throughout — plenty of stock arrives without anyone recording a price, and
    #: refusing to register it until somebody types one would make the register useless.
    unit_price: Decimal | None = None
    status: str = "available"
    note: str | None = None
    #: Opening stock, recorded as a purchase movement so the running total starts explained.
    initial_quantity: int = 0


class InventoryItemUpdate(BaseModel):
    """Everything except ``quantity`` — stock only ever moves through a movement."""

    category_slug: str | None = None
    name: str | None = None
    unit: str | None = None
    min_quantity: int | None = None
    unit_price: Decimal | None = None
    status: str | None = None
    note: str | None = None


class MovementCreate(BaseModel):
    #: Signed. Positive adds, negative removes; the caller decides, so the server never has
    #: to guess what a reason means.
    delta: int
    reason: str
    unit_price: Decimal | None = None
    note: str | None = None


class MovementResponse(BaseModel):
    id: int
    item_id: int
    item_name: str | None = None
    delta: int
    reason: str
    reason_label: str
    request_id: int | None
    request_number: str | None = None
    employee_name: str | None = None
    unit_price: Decimal | None
    total_price: Decimal | None
    note: str | None
    attachments: list[InventoryAttachmentResponse] = []
    created_at: datetime

    @classmethod
    def from_movement(cls, m) -> "MovementResponse":
        return cls(
            id=m.id,
            item_id=m.item_id,
            item_name=m.item.name if m.item else None,
            delta=m.delta,
            reason=m.reason,
            reason_label=movement_reason_label(m.reason),
            request_id=m.request_id,
            request_number=f"RTM-{m.request_id:06d}" if m.request_id else None,
            employee_name=m.employee.full_name if m.employee else None,
            unit_price=m.unit_price,
            total_price=m.total_price,
            note=m.note,
            attachments=[InventoryAttachmentResponse.from_attachment(a) for a in m.attachments],
            created_at=m.created_at,
        )


class InventoryItemResponse(BaseModel):
    id: int
    category_slug: str
    category_label: str | None = None
    name: str
    unit: str
    quantity: int
    min_quantity: int
    is_low: bool
    status: str
    status_label: str
    unit_price: Decimal | None
    note: str | None
    attachments: list[InventoryAttachmentResponse] = []
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_item(cls, item) -> "InventoryItemResponse":
        return cls(
            id=item.id,
            category_slug=item.category_slug,
            category_label=item.category.label_uz if item.category else None,
            name=item.name,
            unit=item.unit,
            quantity=item.quantity,
            min_quantity=item.min_quantity,
            is_low=item.is_low,
            status=item.status,
            status_label=inventory_status_label(item.status),
            unit_price=item.unit_price,
            note=item.note,
            attachments=[
                InventoryAttachmentResponse.from_attachment(a) for a in item.attachments
            ],
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class InventorySummary(BaseModel):
    """The numbers the register's header answers at a glance."""

    total_items: int = 0
    in_stock_items: int = 0
    low_items: int = 0
    planned_items: int = 0
    #: Value of everything on the shelf that has a recorded price. Items without one are
    #: simply absent from it rather than counted as free.
    stock_value: Decimal | None = None
    spent_this_month: Decimal | None = None
    consumed_this_month: int = 0
