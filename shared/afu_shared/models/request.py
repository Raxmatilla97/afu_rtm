from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.enums import RequestStatus
from afu_shared.models.base import Base, TimestampMixin
from afu_shared.models.category import Category
from afu_shared.models.employee import Employee


class Request(TimestampMixin, Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    requester_employee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=False, index=True
    )
    requester: Mapped["Employee"] = relationship(
        "Employee", foreign_keys=[requester_employee_id], lazy="selectin"
    )

    category_slug: Mapped[str] = mapped_column(String(40), ForeignKey("categories.slug"), nullable=False)
    category: Mapped["Category"] = relationship("Category", lazy="selectin")

    description: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String, nullable=False, default=RequestStatus.NEW.value, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False)

    assigned_to_employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=True, index=True
    )
    assigned_to: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[assigned_to_employee_id], lazy="selectin"
    )
    assigned_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completion_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Request id={self.id} status={self.status!r}>"

    @property
    def display_number(self) -> str:
        return f"RTM-{self.id:06d}"
