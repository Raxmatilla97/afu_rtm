"""The RTM inventory register.

Readable by any RTM staff member — they are the people who need to know whether the part
is on the shelf before they promise a repair — and writable only by an admin or supervisor,
because a stock level everyone can edit is a stock level nobody trusts.

Stock is never assigned directly here. Every change goes through
``afu_shared.inventory.record_movement``, which writes the row that explains it.
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import InventoryStatus, MovementReason
from afu_shared.inventory import NotEnoughStock, record_movement
from afu_shared.models import (
    Employee,
    InventoryAttachment,
    InventoryCategory,
    InventoryItem,
    InventoryMovement,
    User,
)
from afu_shared.settings import settings
from app.deps import get_current_caller, get_db
from app.schemas.inventory import (
    InventoryAttachmentResponse,
    InventoryCategoryResponse,
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
    InventorySummary,
    MovementCreate,
    MovementResponse,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _can_read(caller: User | Employee) -> None:
    """Anyone who works on requests. Knowing what is in stock is part of doing the job."""
    if isinstance(caller, User):
        return
    if caller.is_rtm_staff and caller.is_eligible:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="RTM xodimlari uchun")


def _can_write(caller: User | Employee) -> None:
    if isinstance(caller, User):
        return
    if caller.can_manage_assignments:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Inventarni faqat Boshliq yoki Admin o'zgartira oladi",
    )


def _actor_ids(caller: User | Employee) -> tuple[int | None, int | None]:
    """(employee_id, user_id) — exactly one is set, and movements record which."""
    if isinstance(caller, Employee):
        return caller.id, None
    return None, caller.id


@router.get("/categories", response_model=list[InventoryCategoryResponse])
async def list_categories(
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> list[InventoryCategoryResponse]:
    _can_read(caller)
    counts = dict(
        (
            await session.execute(
                select(InventoryItem.category_slug, func.count())
                .where(InventoryItem.status != InventoryStatus.ARCHIVED.value)
                .group_by(InventoryItem.category_slug)
            )
        ).all()
    )
    categories = (
        await session.execute(
            select(InventoryCategory).order_by(
                InventoryCategory.sort_order, InventoryCategory.label_uz
            )
        )
    ).scalars()
    return [
        InventoryCategoryResponse(
            slug=c.slug,
            label_uz=c.label_uz,
            sort_order=c.sort_order,
            is_active=c.is_active,
            item_count=counts.get(c.slug, 0),
        )
        for c in categories
    ]


@router.get("/summary", response_model=InventorySummary)
async def inventory_summary(
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> InventorySummary:
    _can_read(caller)

    live = InventoryItem.status != InventoryStatus.ARCHIVED.value
    total, in_stock, low, planned = (
        await session.execute(
            select(
                func.count().filter(live),
                func.count().filter(live, InventoryItem.quantity > 0),
                func.count().filter(
                    live,
                    InventoryItem.min_quantity > 0,
                    InventoryItem.quantity <= InventoryItem.min_quantity,
                ),
                func.count().filter(
                    InventoryItem.status.in_(
                        (InventoryStatus.PLANNED.value, InventoryStatus.ORDERED.value)
                    )
                ),
            ).select_from(InventoryItem)
        )
    ).one()

    stock_value = (
        await session.execute(
            select(func.sum(InventoryItem.quantity * InventoryItem.unit_price)).where(
                live, InventoryItem.unit_price.isnot(None)
            )
        )
    ).scalar()

    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    spent = (
        await session.execute(
            select(func.sum(InventoryMovement.delta * InventoryMovement.unit_price)).where(
                InventoryMovement.reason == MovementReason.PURCHASE.value,
                InventoryMovement.unit_price.isnot(None),
                InventoryMovement.created_at >= month_start,
            )
        )
    ).scalar()
    consumed = (
        await session.execute(
            select(func.coalesce(func.sum(-InventoryMovement.delta), 0)).where(
                InventoryMovement.reason == MovementReason.CONSUMPTION.value,
                InventoryMovement.created_at >= month_start,
            )
        )
    ).scalar_one()

    return InventorySummary(
        total_items=total or 0,
        in_stock_items=in_stock or 0,
        low_items=low or 0,
        planned_items=planned or 0,
        stock_value=stock_value,
        spent_this_month=spent,
        consumed_this_month=int(consumed or 0),
    )


@router.get("/items", response_model=list[InventoryItemResponse])
async def list_items(
    q: str | None = None,
    category_slug: str | None = None,
    only_low: bool = False,
    include_archived: bool = False,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> list[InventoryItemResponse]:
    _can_read(caller)

    stmt = select(InventoryItem)
    if not include_archived:
        stmt = stmt.where(InventoryItem.status != InventoryStatus.ARCHIVED.value)
    if category_slug:
        stmt = stmt.where(InventoryItem.category_slug == category_slug)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(InventoryItem.name.ilike(like), InventoryItem.note.ilike(like)))
    if only_low:
        stmt = stmt.where(
            InventoryItem.min_quantity > 0,
            InventoryItem.quantity <= InventoryItem.min_quantity,
        )

    stmt = stmt.order_by(InventoryItem.name).limit(500)
    return [InventoryItemResponse.from_item(i) for i in (await session.execute(stmt)).scalars()]


@router.post("/items", response_model=InventoryItemResponse)
async def create_item(
    payload: InventoryItemCreate,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> InventoryItemResponse:
    _can_write(caller)

    if await session.get(InventoryCategory, payload.category_slug) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kategoriya topilmadi")

    item = InventoryItem(
        category_slug=payload.category_slug,
        name=payload.name.strip(),
        unit=payload.unit.strip() or "dona",
        min_quantity=max(0, payload.min_quantity),
        unit_price=payload.unit_price,
        status=payload.status,
        note=payload.note,
        quantity=0,
    )
    session.add(item)
    await session.flush()

    if payload.initial_quantity > 0:
        # Opening stock as a purchase, not as a starting number: the running total is only
        # trustworthy if literally every unit on the shelf arrived through a movement.
        employee_id, user_id = _actor_ids(caller)
        await record_movement(
            session,
            item,
            delta=payload.initial_quantity,
            reason=MovementReason.PURCHASE,
            employee_id=employee_id,
            user_id=user_id,
            unit_price=payload.unit_price,
            note="Boshlang'ich qoldiq",
        )

    await session.flush()
    await session.refresh(item)
    return InventoryItemResponse.from_item(item)


@router.get("/items/{item_id}", response_model=InventoryItemResponse)
async def get_item(
    item_id: int,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> InventoryItemResponse:
    _can_read(caller)
    item = await session.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topilmadi")
    return InventoryItemResponse.from_item(item)


@router.post("/items/{item_id}", response_model=InventoryItemResponse)
async def update_item(
    item_id: int,
    payload: InventoryItemUpdate,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> InventoryItemResponse:
    """POST rather than PATCH — the WAF in front of this app only forwards GET/POST/HEAD."""
    _can_write(caller)
    item = await session.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topilmadi")

    for field in ("category_slug", "name", "unit", "min_quantity", "unit_price", "status", "note"):
        value = getattr(payload, field)
        if value is not None:
            setattr(item, field, value)

    await session.flush()
    await session.refresh(item)
    return InventoryItemResponse.from_item(item)


@router.get("/items/{item_id}/movements", response_model=list[MovementResponse])
async def item_movements(
    item_id: int,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> list[MovementResponse]:
    _can_read(caller)
    rows = (
        await session.execute(
            select(InventoryMovement)
            .where(InventoryMovement.item_id == item_id)
            .order_by(InventoryMovement.id.desc())
            .limit(200)
        )
    ).scalars()
    return [MovementResponse.from_movement(m) for m in rows]


@router.post("/items/{item_id}/movements", response_model=MovementResponse)
async def add_movement(
    item_id: int,
    payload: MovementCreate,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> MovementResponse:
    _can_write(caller)
    item = await session.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topilmadi")

    try:
        reason = MovementReason(payload.reason)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Noma'lum sabab")

    employee_id, user_id = _actor_ids(caller)
    try:
        movement = await record_movement(
            session,
            item,
            delta=payload.delta,
            reason=reason,
            employee_id=employee_id,
            user_id=user_id,
            unit_price=payload.unit_price,
            note=payload.note,
        )
    except NotEnoughStock as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Omborda faqat {exc.item.quantity} {exc.item.unit} bor",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await session.refresh(movement)
    return MovementResponse.from_movement(movement)


@router.get("/movements", response_model=list[MovementResponse])
async def recent_movements(
    reason: str | None = None,
    request_id: int | None = None,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> list[MovementResponse]:
    """The register's activity feed, and the answer to "what did this job consume?"."""
    _can_read(caller)
    stmt = select(InventoryMovement)
    if reason:
        stmt = stmt.where(InventoryMovement.reason == reason)
    if request_id is not None:
        stmt = stmt.where(InventoryMovement.request_id == request_id)
    stmt = stmt.order_by(InventoryMovement.id.desc()).limit(200)
    return [MovementResponse.from_movement(m) for m in (await session.execute(stmt)).scalars()]


@router.post("/items/{item_id}/attachments", response_model=InventoryAttachmentResponse)
async def upload_attachment(
    item_id: int,
    file: UploadFile = File(...),
    movement_id: int | None = Form(default=None),
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> InventoryAttachmentResponse:
    """A receipt or invoice. Optional everywhere — see the item model."""
    _can_write(caller)
    item = await session.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topilmadi")

    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Fayl {MAX_UPLOAD_BYTES // (1024 * 1024)} MB dan oshmasligi kerak",
        )

    if movement_id is not None:
        movement = await session.get(InventoryMovement, movement_id)
        if movement is None or movement.item_id != item_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Harakat topilmadi"
            )

    suffix = Path(file.filename or "").suffix.lower()[:8] or ".bin"
    stored = f"{uuid.uuid4().hex}{suffix}"
    target_dir = Path(settings.storage_root) / "inventory" / str(item_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / stored).write_bytes(payload)

    employee_id, user_id = _actor_ids(caller)
    attachment = InventoryAttachment(
        item_id=item_id,
        movement_id=movement_id,
        file_path=f"inventory/{item_id}/{stored}",
        original_filename=file.filename,
        content_type=file.content_type,
        file_size=len(payload),
        uploaded_by_employee_id=employee_id,
        uploaded_by_user_id=user_id,
    )
    session.add(attachment)
    await session.flush()
    await session.refresh(attachment)
    return InventoryAttachmentResponse.from_attachment(attachment)


@router.get("/items/{item_id}/attachments/{attachment_id}")
async def download_attachment(
    item_id: int,
    attachment_id: int,
    download: bool = False,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
):
    _can_read(caller)
    attachment = await session.get(InventoryAttachment, attachment_id)
    if attachment is None or attachment.item_id != item_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topilmadi")

    full_path = Path(settings.storage_root) / attachment.file_path
    if not full_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fayl topilmadi")

    name = attachment.original_filename or full_path.name
    disposition = "attachment" if download else "inline"
    return FileResponse(
        full_path,
        media_type=attachment.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="'
                + name.encode("ascii", "replace").decode("ascii").replace('"', "_")
                + '"'
            )
        },
    )
