"""Reading a request's files back out of the database."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import MessageVisibility
from afu_shared.models import RequestAttachment, RequestMessage


async def attachments_for_request(
    session: AsyncSession, request_id: int, *, include_internal: bool = True
) -> list[RequestAttachment]:
    """Every file on a request, oldest first.

    ``include_internal=False`` drops files that hang off an internal RTM note. The
    requester must never be shown those, and filtering here — where the join to
    ``request_messages`` lives — keeps that rule in one place rather than in each screen
    that happens to list files.
    """
    stmt = (
        select(RequestAttachment)
        .where(RequestAttachment.request_id == request_id)
        .order_by(RequestAttachment.id)
    )
    if not include_internal:
        stmt = (
            stmt.outerjoin(RequestMessage, RequestAttachment.message_id == RequestMessage.id)
            .where(
                (RequestAttachment.message_id.is_(None))
                | (RequestMessage.visibility == MessageVisibility.TO_REQUESTER.value)
            )
        )
    return list((await session.execute(stmt)).scalars())
