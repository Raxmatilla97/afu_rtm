from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.models.base import Base
from afu_shared.models.employee import Employee
from afu_shared.models.request import Request


class RequestAttachment(Base):
    __tablename__ = "request_attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("requests.id"), nullable=False, index=True
    )
    request: Mapped["Request"] = relationship("Request")

    uploaded_by_employee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=False
    )
    uploaded_by: Mapped["Employee"] = relationship("Employee")

    file_path: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<RequestAttachment id={self.id} request_id={self.request_id}>"
