from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.enums import RequestStatus
from afu_shared.models.base import Base, TimestampMixin
from afu_shared.models.category import Category
from afu_shared.models.employee import Employee

if TYPE_CHECKING:
    # Both import ``Request``, so naming them at runtime would close the circle. SQLAlchemy
    # resolves the relationship targets from these strings once every model is registered.
    from afu_shared.models.rating import Rating
    from afu_shared.models.request_assignee import RequestAssignee


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

    #: The plain reading of the request, and the only form Telegram ever sees — every
    #: bot card, briefing and warning escapes this string. Derived from
    #: ``description_html`` when the web form was used, so the two cannot disagree.
    description: Mapped[str] = mapped_column(Text, nullable=False)
    #: What the web form produced, already reduced to the allowlist in
    #: ``afu_shared.richtext``. Null for everything filed through the bot, which has no
    #: formatting to offer — the web then falls back to rendering ``description``.
    description_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String, nullable=False, default=RequestStatus.NEW.value, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False)

    #: ``"boshliq"``, ``"admin"`` or null — which management role filed this, stamped once
    #: at creation by ``afu_shared.people.role_of``. Stored rather than re-derived from the
    #: requester's flags because the group card is edited in place for the request's whole
    #: life: a Boshliq who is later demoted would otherwise retroactively turn every
    #: directive they ever issued back into an ordinary request, including ones already
    #: being worked on because of who asked.
    requester_role: Mapped[str | None] = mapped_column(String(16), nullable=True)

    assigned_to_employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=True, index=True
    )
    assigned_to: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[assigned_to_employee_id], lazy="selectin"
    )
    #: Read-only view of the whole team. ``viewonly`` on purpose: writes go through
    #: ``afu_shared.assignments``, which also keeps ``assigned_to_employee_id`` and the
    #: status in step. A second way to mutate the same rows is how those three drift apart.
    #: ``selectin`` means listing a page of requests costs one extra query, not one per row.
    assignees: Mapped[list["RequestAssignee"]] = relationship(
        "RequestAssignee",
        lazy="selectin",
        viewonly=True,
        order_by="[RequestAssignee.is_primary.desc(), RequestAssignee.assigned_at]",
    )

    #: What the reporter thought of the service, once they said. One row per person who
    #: worked on it — the requester rates the service and everyone who delivered it carries
    #: the score — so this is a list even though the reporter only ever pressed once, and
    #: anything reading "the rating" wants ``ratings[0]``.
    #:
    #: ``viewonly`` and ``selectin`` for the same reasons as ``assignees`` above: rating is
    #: written in one place, and a page of requests costs one extra query rather than one
    #: per row. It is here at all because without it the web could not tell an unrated
    #: request from a rated one — the stars reset on every reload and the reporter was left
    #: pressing a button that appeared to do nothing.
    ratings: Mapped[list["Rating"]] = relationship(
        "Rating", lazy="selectin", viewonly=True, order_by="Rating.id"
    )

    assigned_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Set while the request sits in waiting: when the part is expected, and why it is
    #: blocked. The date is a promise to the reporter, so it is stored rather than derived —
    #: "we are waiting" without a date is what makes people give up and call instead.
    waiting_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    waiting_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completion_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Why a Boshliq or Admin sent this back, and when. Stored on the request rather than
    #: left in the status history because it is the first thing every side has to read —
    #: the reporter's notification, the reporter's screen in the bot, the group card and
    #: the web page all show it, and none of them should have to dig through history for
    #: the one sentence that explains the state they are looking at.
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    return_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: When the "this is late" warning went out. The overdue sweep runs on a schedule, so
    #: without a record of having warned it would re-warn the same request every half hour
    #: until somebody closed it — and a warning that repeats is one people learn to ignore.
    #: Cleared whenever the deadline moves, which makes a new deadline warnable again.
    overdue_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<Request id={self.id} status={self.status!r}>"

    @property
    def display_number(self) -> str:
        return f"RTM-{self.id:06d}"
