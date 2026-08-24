from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.enums import AttachmentKind
from afu_shared.models.base import Base
from afu_shared.models.employee import Employee
from afu_shared.models.request import Request

if TYPE_CHECKING:
    from afu_shared.models.request_message import RequestMessage


class RequestAttachment(Base):
    """A file on a request — or, when ``message_id`` is set, on one message inside it.

    Two identifiers are kept for every file, and both matter:

    * ``file_path`` is our own copy on disk, which is what the web interface serves.
    * ``telegram_file_id`` is Telegram's handle, which lets the bot re-send a voice message
      or a round video to somebody else *as that kind of media* — instantly, without
      uploading anything. Relaying a requester's evidence to the assigned RTM staffer is
      the whole point, and re-uploading a downloaded copy would both cost a round trip and
      arrive as a plain file.

    Either identifier may be missing: files above the Bot API's 20 MB download ceiling keep
    only the Telegram handle, and web uploads never have one.
    """

    __tablename__ = "request_attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("requests.id"), nullable=False, index=True
    )
    request: Mapped["Request"] = relationship("Request")

    #: NULL means the file belongs to the request itself (the original submission).
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("request_messages.id"), nullable=True, index=True
    )
    message: Mapped["RequestMessage | None"] = relationship(
        "RequestMessage", back_populates="attachments"
    )

    uploaded_by_employee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=False
    )
    uploaded_by: Mapped["Employee"] = relationship("Employee")

    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AttachmentKind.DOCUMENT.value
    )

    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Voice, audio, video and video notes only.
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    telegram_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    #: Stable across bots and re-sends; the only safe key for "is this the same file".
    telegram_file_unique_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<RequestAttachment id={self.id} request_id={self.request_id} kind={self.kind!r}>"
