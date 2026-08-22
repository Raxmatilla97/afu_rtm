from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.enums import HemisSyncStatus
from afu_shared.models.base import Base
from afu_shared.models.user import User


class HemisSyncRun(Base):
    __tablename__ = "hemis_sync_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default=HemisSyncStatus.RUNNING.value)

    triggered_by_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    triggered_by: Mapped["User"] = relationship("User")

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    departments_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    departments_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    employees_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    employees_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    employees_revoked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<HemisSyncRun id={self.id} status={self.status!r}>"
