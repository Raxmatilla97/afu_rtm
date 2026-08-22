from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from afu_shared.models.base import Base


class Category(Base):
    __tablename__ = "categories"

    slug: Mapped[str] = mapped_column(String(40), primary_key=True)
    label_uz: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Category slug={self.slug!r} label_uz={self.label_uz!r}>"
