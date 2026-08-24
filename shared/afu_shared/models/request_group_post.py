from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.models.base import Base
from afu_shared.models.request import Request


class RequestGroupPost(Base):
    """The card for one request in one group chat.

    Remembering the message id is what makes the group readable: a request announces itself
    once and that same card is then edited as people take it and finish it. Posting a fresh
    message for every state change would bury the group in noise on a busy day, and the
    "take it" buttons on the older copies would still be live.
    """

    __tablename__ = "request_group_posts"

    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("requests.id"), primary_key=True
    )
    request: Mapped["Request"] = relationship("Request")

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<RequestGroupPost request_id={self.request_id} chat_id={self.chat_id}>"
