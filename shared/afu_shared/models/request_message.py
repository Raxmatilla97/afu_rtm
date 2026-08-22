from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.models.base import Base
from afu_shared.models.employee import Employee
from afu_shared.models.request import Request
from afu_shared.models.user import User


class RequestMessage(Base):
    __tablename__ = "request_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("requests.id"), nullable=False, index=True
    )
    request: Mapped["Request"] = relationship("Request")

    author_employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=True
    )
    author_employee: Mapped["Employee | None"] = relationship("Employee")

    author_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    author_user: Mapped["User | None"] = relationship("User")

    visibility: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<RequestMessage id={self.id} request_id={self.request_id} visibility={self.visibility!r}>"
