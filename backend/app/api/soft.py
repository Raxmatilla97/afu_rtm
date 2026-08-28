"""RTM Soft: uploading the driver and software shelf the bot hands out.

Readable by any signed-in employee — the whole point is that people can find a driver
themselves — and writable by an admin or supervisor.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Employee, SoftAsset, SoftCategory, User
from afu_shared.settings import settings
from app.deps import get_current_caller, get_db
from app.downloads import serve_headers
from app.schemas.soft import SoftAssetResponse, SoftAssetUpdate, SoftCategoryResponse

router = APIRouter(prefix="/soft", tags=["soft"])

#: Drivers are big. Kept in step with nginx's client_max_body_size, which would otherwise
#: reject the upload before FastAPI ever saw it.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _can_write(caller: User | Employee) -> None:
    if isinstance(caller, User):
        return
    if caller.can_manage_assignments:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Faqat Boshliq yoki Admin fayl qo'sha oladi",
    )


@router.get("/categories", response_model=list[SoftCategoryResponse])
async def list_categories(
    _: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> list[SoftCategoryResponse]:
    counts = dict(
        (
            await session.execute(
                select(SoftAsset.category_slug, func.count())
                .where(SoftAsset.is_active.is_(True))
                .group_by(SoftAsset.category_slug)
            )
        ).all()
    )
    categories = (
        await session.execute(
            select(SoftCategory).order_by(SoftCategory.sort_order, SoftCategory.label_uz)
        )
    ).scalars()
    return [
        SoftCategoryResponse(
            slug=c.slug,
            label_uz=c.label_uz,
            sort_order=c.sort_order,
            is_active=c.is_active,
            asset_count=counts.get(c.slug, 0),
        )
        for c in categories
    ]


@router.get("/assets", response_model=list[SoftAssetResponse])
async def list_assets(
    category_slug: str | None = None,
    q: str | None = None,
    _: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> list[SoftAssetResponse]:
    stmt = select(SoftAsset)
    if category_slug:
        stmt = stmt.where(SoftAsset.category_slug == category_slug)
    if q:
        stmt = stmt.where(SoftAsset.title.ilike(f"%{q}%"))
    stmt = stmt.order_by(SoftAsset.category_slug, SoftAsset.title).limit(500)
    return [SoftAssetResponse.from_asset(a) for a in (await session.execute(stmt)).scalars()]


@router.post("/assets", response_model=SoftAssetResponse)
async def upload_asset(
    file: UploadFile = File(...),
    category_slug: str = Form(...),
    title: str = Form(...),
    version: str | None = Form(default=None),
    description: str | None = Form(default=None),
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> SoftAssetResponse:
    _can_write(caller)

    if await session.get(SoftCategory, category_slug) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kategoriya topilmadi")

    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Fayl {MAX_UPLOAD_BYTES // (1024 * 1024)} MB dan oshmasligi kerak",
        )

    suffix = Path(file.filename or "").suffix.lower()[:10] or ".bin"
    stored = f"{uuid.uuid4().hex}{suffix}"
    target_dir = Path(settings.storage_root) / "soft" / category_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / stored).write_bytes(payload)

    asset = SoftAsset(
        category_slug=category_slug,
        title=title.strip(),
        version=(version or "").strip() or None,
        description=(description or "").strip() or None,
        file_path=f"soft/{category_slug}/{stored}",
        original_filename=file.filename,
        content_type=file.content_type,
        file_size=len(payload),
        uploaded_by_employee_id=caller.id if isinstance(caller, Employee) else None,
        uploaded_by_user_id=caller.id if isinstance(caller, User) else None,
    )
    session.add(asset)
    await session.flush()
    await session.refresh(asset)
    return SoftAssetResponse.from_asset(asset)


@router.post("/assets/{asset_id}", response_model=SoftAssetResponse)
async def update_asset(
    asset_id: int,
    payload: SoftAssetUpdate,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> SoftAssetResponse:
    _can_write(caller)
    asset = await session.get(SoftAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topilmadi")

    for field in ("category_slug", "title", "version", "description", "is_active"):
        value = getattr(payload, field)
        if value is not None:
            setattr(asset, field, value)

    await session.flush()
    await session.refresh(asset)
    return SoftAssetResponse.from_asset(asset)


@router.post("/assets/{asset_id}/delete", response_model=SoftAssetResponse)
async def deactivate_asset(
    asset_id: int,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> SoftAssetResponse:
    """Hidden rather than deleted.

    Telegram still holds copies handed out earlier, and a row that disappears takes its
    download history with it. Deactivating stops it being offered and keeps the record.
    """
    _can_write(caller)
    asset = await session.get(SoftAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topilmadi")
    asset.is_active = False
    await session.flush()
    await session.refresh(asset)
    return SoftAssetResponse.from_asset(asset)


@router.get("/assets/{asset_id}/download")
async def download_asset(
    asset_id: int,
    _: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
):
    asset = await session.get(SoftAsset, asset_id)
    if asset is None or not asset.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topilmadi")

    full_path = Path(settings.storage_root) / asset.file_path
    if not full_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fayl topilmadi")

    asset.download_count += 1
    name = asset.original_filename or full_path.name
    # Always a download: these are drivers and installers, and want_download=True also
    # pins the type to octet-stream so an uploaded .html can never render on our origin.
    media_type, headers = serve_headers(asset.content_type, name, want_download=True)
    return FileResponse(full_path, media_type=media_type, headers=headers)
