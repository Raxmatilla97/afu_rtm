from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.models.base import Base
from afu_shared.models.employee import Employee
from afu_shared.models.request import Request


class Rating(Base):
    """One score, recorded against one of the people who did the work.

    A request may now be worked by several staff, so the requester's single act of rating
    produces one row per assignee. The uniqueness is therefore on the pair, not on the
    request alone: rating twice is still impossible, but crediting only the person who
    happened to press the button first would quietly erase a colleague's contribution from
    the leaderboard.
    """

    __tablename__ = "ratings"
    __table_args__ = (
        CheckConstraint("score >= 1 AND score <= 5", name="ck_ratings_score_1_5"),
        UniqueConstraint("request_id", "rated_employee_id", name="uq_ratings_request_employee"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("requests.id"), nullable=False, index=True
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
