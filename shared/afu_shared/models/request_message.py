from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.models.base import Base
from afu_shared.models.employee import Employee
from afu_shared.models.request import Request
from afu_shared.models.user import User

if TYPE_CHECKING:
    from afu_shared.models.request_attachment import RequestAttachment


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
    #: Nullable since messages carry media: a voice note or a round video is a complete
    #: message on its own, and forcing an empty string there would make "no text" and
    #: "text the author deleted" indistinguishable.
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    attachments: Mapped[list["RequestAttachment"]] = relationship(
        "RequestAttachment",
        back_populates="message",
        lazy="selectin",
        order_by="RequestAttachment.id",
    )

    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<RequestMessage id={self.id} request_id={self.request_id} visibility={self.visibility!r}>"
