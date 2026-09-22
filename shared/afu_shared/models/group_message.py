from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.models.base import Base
from afu_shared.models.request import Request


class GroupMessage(Base):
    """Everything the bot has put into an RTM group that is *not* a request card.

    The cards are already remembered, one per request, in ``RequestGroupPost`` — that row
    exists so the card can be edited in place, which is the whole design of the group feed.
    This table is the other half: the short reply lines under a card ("X took this on"), the
    overdue alarms, the welcome notice, the files replayed by the 📎 button. Between the two
    of them, the admin panel can answer "what is the bot showing the group right now?" —
    which it could not before, because three quarters of those messages were fire-and-forget.

    Deliberately **not** merged with ``RequestGroupPost``. Storing a card's
    ``(chat_id, message_id)`` in both places would mean two rows that have to agree about
    one Telegram message, and the one thing a message id must never be is ambiguous. The
    admin list unions the two queries instead; see ``app.api.group_messages``.

    A row here is a claim that the message *existed*, not that it still does: a moderator
    can delete anything from a group without telling us. The panel treats a delete that
    Telegram refuses as "already gone" and drops the row, which is the only honest
    reconciliation available without polling every message.
    """

    __tablename__ = "group_messages"
    __table_args__ = (
        # One row per Telegram message. Makes the delete path idempotent and stops a
        # retried worker job from logging the same post twice.
        UniqueConstraint("chat_id", "message_id", name="uq_group_messages_chat_message"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    #: No relationship on purpose. The panel lists these alongside request cards, which come
    #: from a table that has no chat relationship either, so it resolves both sets of titles
    #: from one dictionary — an eager loader here would only add a query nothing reads.
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("notification_chats.chat_id"), nullable=False, index=True
    )

    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    #: ``note`` | ``overdue`` | ``welcome`` | ``notice`` | ``files``. A plain string rather
    #: than an enum column: this is a label for a human reading a list, and a new kind of
    #: bot message should not need a migration before it can be listed and deleted.
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    #: The job this message is about, when it is about one. Nulled rather than cascaded on
    #: request deletion — see ``_purge_request``, which also deletes these from Telegram.
    request_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("requests.id"), nullable=True, index=True
    )
    request: Mapped["Request | None"] = relationship("Request", lazy="selectin")

    #: What the message says, already stripped of markup and truncated. Stored rather than
    #: rebuilt because most of these cannot be rebuilt: the text a reply line carried
    #: depended on who pressed what, and that moment is gone.
    preview: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Set for messages the bot already intends to delete by itself — the replayed files,
    #: which live ten minutes. The list hides them once past, so the panel never offers a
    #: delete button for something that is no longer on screen.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<GroupMessage chat_id={self.chat_id} message_id={self.message_id} kind={self.kind!r}>"
