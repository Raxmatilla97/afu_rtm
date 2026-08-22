from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.models.base import Base
from afu_shared.models.employee import Employee
from afu_shared.models.request import Request


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (CheckConstraint("score >= 1 AND score <= 5", name="ck_ratings_score_1_5"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("requests.id"), unique=True, nullable=False
    )
    request: Mapped["Request"] = relationship("Request")

    rated_employee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=False, index=True
    )
    rated_employee: Mapped["Employee"] = relationship("Employee", foreign_keys=[rated_employee_id])

    rated_by_employee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=False
    )
    rated_by_employee: Mapped["Employee"] = relationship("Employee", foreign_keys=[rated_by_employee_id])

    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Rating id={self.id} request_id={self.request_id} score={self.score}>"
