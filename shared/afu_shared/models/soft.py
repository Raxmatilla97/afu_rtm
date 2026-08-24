"""RTM Soft: the driver and software shelf.

Files are uploaded once on the web and handed out by the bot. The bot never re-uploads:
the Telegram file id it gets back on the first send is cached on the row, so the second
person to ask for the same 400 MB driver gets it instantly and the server does no work.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.models.base import Base, TimestampMixin


class SoftCategory(Base):
    __tablename__ = "soft_categories"

    slug: Mapped[str] = mapped_column(String(40), primary_key=True)
    label_uz: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    assets: Mapped[list["SoftAsset"]] = relationship(
        "SoftAsset", back_populates="category", order_by="SoftAsset.title"
    )

    def __repr__(self) -> str:
        return f"<SoftCategory slug={self.slug!r}>"


class SoftAsset(TimestampMixin, Base):
    __tablename__ = "soft_assets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    category_slug: Mapped[str] = mapped_column(
        String(40), ForeignKey("soft_categories.slug"), nullable=False, index=True
    )
    category: Mapped["SoftCategory"] = relationship(
        "SoftCategory", back_populates="assets", lazy="selectin"
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Version, OS, anything that decides *which* of four similar drivers is the right one.
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    file_path: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    #: Filled in the first time the bot sends this file, and reused forever after. Cleared
    #: whenever the file itself is replaced, or Telegram would keep handing out the old one.
    telegram_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    uploaded_by_employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=True
    )
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<SoftAsset id={self.id} title={self.title!r}>"
