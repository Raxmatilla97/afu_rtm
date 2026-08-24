from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.models.base import Base
from afu_shared.models.employee import Employee


class NotificationChat(Base):
    """A Telegram group the bot broadcasts request activity into.

    Registered by being *used*: an RTM staff member adds the bot to their group and the bot
    records the chat. There is no chat id to copy into ``.env`` and no risk of it going
    stale after a group is upgraded to a supergroup (which changes the id).

    Who added the bot is the whole access check. A group registers only if the person who
    added it is a linked, eligible RTM staff member — otherwise anyone could add this bot
    to any chat and receive every request, with reporters' names and phone numbers in them.
    """

    __tablename__ = "notification_chats"

    #: Telegram's own chat id. Negative for groups, and the natural primary key — the same
    #: group can never be registered twice.
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chat_type: Mapped[str | None] = mapped_column(String(24), nullable=True)

    #: Cleared rather than deleted when the bot is removed, so re-adding it restores the
    #: group's history of posts instead of orphaning them.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    registered_by_employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=True
    )
    registered_by: Mapped["Employee | None"] = relationship("Employee")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<NotificationChat chat_id={self.chat_id} active={self.is_active}>"
