"""Who did what, and when — the record the admin panel reads.

Nothing else in this database answers "is anybody actually using the bot?" or "what did
this person do last?". Requests and messages record outcomes, not use: somebody who opened
the bot, read their tasks and closed it leaves no trace at all, and neither does a
supervisor who spent the morning reassigning work.

Deliberately append-only and deliberately shallow. It stores a short action key, the actor,
and a human-readable target — never a copy of the content, which lives in its own tables and
would go stale here. Old rows are pruned on a schedule; this is an activity feed, not an
archive.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.models.base import Base
from afu_shared.models.employee import Employee
from afu_shared.models.user import User


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    #: "bot" or "web". The daily-active-users count is per source, because a busy web day
    #: and a busy bot day mean different things about where people actually work.
    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    #: A short stable key like "request.create" or "login.quick". Stable because the panel
    #: groups by it and a renamed key would split one action into two rows in every chart.
    action: Mapped[str] = mapped_column(String(48), nullable=False, index=True)

    employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=True, index=True
    )
    employee: Mapped["Employee | None"] = relationship("Employee", lazy="selectin")

    #: The panel admin account, which has no employee row.
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    user: Mapped["User | None"] = relationship("User", lazy="selectin")

    #: A snapshot of the actor's name. Kept even though the relationship exists, because a
    #: feed has to stay readable after somebody is removed from HEMIS — and because reading
    #: it costs no join.
    actor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    #: What the action was about, in the form a person recognises: "RTM-000042",
    #: "HP 85A toner", a department name. Never an internal id on its own.
    target: Mapped[str | None] = mapped_column(String(200), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ActivityEvent {self.action} by {self.actor_name!r} at {self.created_at}>"
