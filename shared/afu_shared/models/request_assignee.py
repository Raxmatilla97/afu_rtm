from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.models.base import Base
from afu_shared.models.employee import Employee
from afu_shared.models.request import Request
from afu_shared.models.user import User


class RequestAssignee(Base):
    """One RTM staff member working on one request.

    Real jobs are not always one person: a network fault and the switch cabinet behind it
    can need two people, and the group flow lets a second colleague join a request somebody
    has already picked up.

    ``Request.assigned_to_employee_id`` survives alongside this table and holds the
    *primary* assignee — whoever took it first, or whoever the admin named. It stays because
    a single "who owns this" is what lists, filters and the completion notice need to show,
    and because inventing a rule for "the assignee" out of a set on every read would be
    worse than storing the answer once. ``afu_shared.assignments`` keeps the two in step;
    nothing else should write either of them.
    """

    __tablename__ = "request_assignees"

    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("requests.id"), primary_key=True
    )
    request: Mapped["Request"] = relationship("Request")

    employee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("employees.id"), primary_key=True
    )
    employee: Mapped["Employee"] = relationship("Employee", lazy="selectin")

    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: NULL means the employee took the job themselves from the group.
    assigned_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    assigned_by_user: Mapped["User | None"] = relationship("User")

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<RequestAssignee request_id={self.request_id} "
            f"employee_id={self.employee_id} primary={self.is_primary}>"
        )
