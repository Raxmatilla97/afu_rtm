"""Recording what the bot puts into an RTM group, so it can be listed and taken back.

Before this existed, only the request cards were remembered — every other message the bot
sent to a group (the reply line when somebody took a job, the overdue alarm, the welcome
notice, the files replayed by the 📎 button) was fire-and-forget. The admin panel could
therefore answer "which requests have a card" but not the question people actually ask,
which is "what is the bot showing the group right now, and can you take that one down".

Kept in ``shared`` because both the bot and the worker post to groups, and a message
recorded by only one of them is a message the panel cannot delete.

Writing here must never be able to break a send. The message is already in the group by the
time these functions run; raising would roll back the caller's transaction and lose
whatever else it was doing, to fix a bookkeeping row. So every failure is swallowed and
logged, and the worst case is a message the panel does not know about — exactly the state
everything was in before.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import GroupMessage, NotificationChat

logger = logging.getLogger(__name__)

__all__ = [
    "KIND_FILES",
    "KIND_LABELS",
    "KIND_NOTE",
    "KIND_NOTICE",
    "KIND_OVERDUE",
    "KIND_WELCOME",
    "kind_label",
    "preview_of",
    "record_group_message",
]

#: A short reply under a card: somebody took the job, somebody was assigned to it.
KIND_NOTE = "note"
#: The deadline alarm, which is also a reply under the card but is the one message in the
#: group that is shouting. Worth telling apart in a list an admin is scanning for noise.
KIND_OVERDUE = "overdue"
#: The "bot connected" notice posted when a group is registered.
KIND_WELCOME = "welcome"
#: Anything else the bot says to the group on its own behalf — the disconnect notice.
KIND_NOTICE = "notice"
#: Files replayed into the group by a card's 📎 button. These delete themselves; see the
#: ``expires_at`` column.
KIND_FILES = "files"

KIND_LABELS: dict[str, str] = {
    "card": "🎫 Murojaat kartochkasi",
    KIND_NOTE: "💬 Kartochka ostidagi izoh",
    KIND_OVERDUE: "🔴 Muddat ogohlantirishi",
    KIND_WELCOME: "👋 Ulanish xabari",
    KIND_NOTICE: "📢 Bot xabari",
    KIND_FILES: "📎 Yuborilgan fayllar",
}


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")

#: How much of a message the list shows. Long enough to recognise which one it is, short
#: enough that a screen of them is still a list rather than a transcript.
PREVIEW_LIMIT = 300


def preview_of(text: str | None, *, limit: int = PREVIEW_LIMIT) -> str | None:
    """The message as a single line of plain text, for a table cell.

    The stored text is what was *sent*, which is Telegram HTML. Rendering those tags into an
    admin's browser would be both ugly and an injection route — the strings interpolate a
    fault description somebody typed.
    """
    if not text:
        return None
    plain = _SPACE.sub(" ", _TAGS.sub(" ", text)).strip()
    if not plain:
        return None
    return plain if len(plain) <= limit else plain[: limit - 1].rstrip() + "…"


async def record_group_message(
    session: AsyncSession,
    *,
    chat_id: int,
    message_id: int,
    kind: str,
    text: str | None = None,
    request_id: int | None = None,
    ttl_seconds: int | None = None,
) -> None:
    """Remember one message the bot just posted to a group. Never raises.

    Skipped for a chat that was never registered: ``chat_id`` is a foreign key to
    ``notification_chats``, and the bot does answer unregistered chats (it tells whoever
    added it that they may not). Those messages are not part of any group's feed and there
    is nothing in the panel that could list them.
    """
    try:
        if await session.get(NotificationChat, chat_id) is None:
            return
        existing = (
            await session.execute(
                select(GroupMessage).where(
                    GroupMessage.chat_id == chat_id, GroupMessage.message_id == message_id
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return

        # A SAVEPOINT, so that a failure here rolls back this insert and nothing else.
        # Swallowing a plain flush error would leave the caller's transaction poisoned and
        # its commit would raise anyway — which is the opposite of "never breaks a send".
        async with session.begin_nested():
            session.add(
                GroupMessage(
                    chat_id=chat_id,
                    message_id=message_id,
                    kind=kind,
                    request_id=request_id,
                    preview=preview_of(text),
                    expires_at=(
                        datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
                        if ttl_seconds
                        else None
                    ),
                )
            )
    except Exception:  # noqa: BLE001 — see the module docstring: bookkeeping never breaks a send.
        logger.warning(
            "Could not record group message %s in chat %s", message_id, chat_id, exc_info=True
        )
