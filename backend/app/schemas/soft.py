from datetime import datetime

from pydantic import BaseModel


class SoftCategoryResponse(BaseModel):
    slug: str
    label_uz: str
    sort_order: int
    is_active: bool
    asset_count: int = 0


class SoftAssetUpdate(BaseModel):
    category_slug: str | None = None
    title: str | None = None
    version: str | None = None
    description: str | None = None
    is_active: bool | None = None


class SoftAssetResponse(BaseModel):
    id: int
    category_slug: str
    category_label: str | None = None
    title: str
    version: str | None
    description: str | None
    original_filename: str | None
    content_type: str | None
    file_size: int | None
    download_count: int
    is_active: bool
    #: Whether the bot has a Telegram handle for this file yet. Shown in the admin table
    #: because it is the difference between an instant hand-off and a fresh upload.
    is_cached: bool = False
    download_url: str
    last_sent_at: datetime | None
    created_at: datetime

    @classmethod
    def from_asset(cls, a) -> "SoftAssetResponse":
        return cls(
            id=a.id,
            category_slug=a.category_slug,
            category_label=a.category.label_uz if a.category else None,
            title=a.title,
            version=a.version,
            description=a.description,
            original_filename=a.original_filename,
            content_type=a.content_type,
            file_size=a.file_size,
            download_count=a.download_count,
            is_active=a.is_active,
            is_cached=bool(a.telegram_file_id),
            download_url=f"/api/soft/assets/{a.id}/download",
            last_sent_at=a.last_sent_at,
            created_at=a.created_at,
        )
