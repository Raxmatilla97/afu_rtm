from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.enums import TelegramLinkStatus
from afu_shared.models.base import Base
from afu_shared.models.employee import Employee


class TelegramLinkToken(Base):
    __tablename__ = "telegram_link_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)

    employee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=False, index=True
    )
    employee: Mapped["Employee"] = relationship("Employee")

    purpose: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default=TelegramLinkStatus.PENDING.value)

    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<TelegramLinkToken token={self.token!r} status={self.status!r}>"
