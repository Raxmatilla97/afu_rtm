from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.models.base import Base
from afu_shared.models.employee import Employee
from afu_shared.models.request import Request
from afu_shared.models.user import User


class RequestStatusHistory(Base):
    __tablename__ = "request_status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("requests.id"), nullable=False, index=True
    )
    request: Mapped["Request"] = relationship("Request")

    from_status: Mapped[str | None] = mapped_column(String, nullable=True)
    to_status: Mapped[str] = mapped_column(String, nullable=False)

    changed_by_employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=True
    )
    changed_by_employee: Mapped["Employee | None"] = relationship("Employee")

    changed_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    changed_by_user: Mapped["User | None"] = relationship("User")

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<RequestStatusHistory id={self.id} request_id={self.request_id} to_status={self.to_status!r}>"
