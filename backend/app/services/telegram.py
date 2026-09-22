"""The little bit of the Telegram Bot API the panel calls for itself.

Everything else this platform sends to Telegram goes through the worker, and for good
reason: a send that fails should be retried, not thrown at whoever happened to trigger it.
Deleting a message from the admin panel is the exception. The person pressing the button is
watching the row disappear, and "we have queued your request" is not an answer to "is it
still in the group?" — the bot may not be an administrator there, in which case the delete
will never succeed and nobody would ever be told.

So this calls the API directly and reports what actually happened. One HTTP request, a short
timeout, no retries: the panel can simply be pressed again.
"""

import logging
from dataclasses import dataclass

import httpx

from afu_shared.settings import settings

logger = logging.getLogger(__name__)

#: Short on purpose. This runs inside a request the admin is waiting on, and a bulk delete
#: makes one call per message.
TIMEOUT_SECONDS = 10.0

#: What Telegram says when the message is not there any more, or never was. Not an error
#: worth showing: the panel's job was to make it gone, and it is gone.
_ALREADY_GONE = ("message to delete not found", "message identifier is not specified")

#: Telegram's own wording, translated to something an administrator can act on. The first is
#: by far the most common: a bot may only delete other people's messages — and its own after
#: 48 hours — if it is an administrator with "delete messages".
_REASONS = {
    "message can't be deleted": (
        "Telegram bu xabarni o'chirishga ruxsat bermadi. Bot guruhda administrator "
        "bo'lishi va «Xabarlarni o'chirish» huquqiga ega bo'lishi kerak."
    ),
    "not enough rights": (
        "Botda huquq yetarli emas. Guruh sozlamalarida botga administrator va "
        "«Xabarlarni o'chirish» huquqini bering."
    ),
    "chat not found": "Guruh topilmadi — bot u yerdan chiqarib yuborilgan bo'lishi mumkin.",
    "bot was kicked": "Bot bu guruhdan chiqarib yuborilgan.",
}


@dataclass(frozen=True)
class DeleteOutcome:
    """``ok`` covers both "we deleted it" and "it was already gone".

    They are one outcome from the panel's point of view — the row should go either way —
    but they are told apart in ``already_gone`` so the reply can say which, rather than
    claiming credit for a message a moderator removed last week.
    """

    ok: bool
    already_gone: bool = False
    error: str | None = None


async def delete_message(chat_id: int, message_id: int) -> DeleteOutcome:
    token = settings.telegram_bot_token.strip()
    if not token:
        return DeleteOutcome(ok=False, error="Telegram bot tokeni sozlanmagan")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/deleteMessage",
                json={"chat_id": chat_id, "message_id": message_id},
            )
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("deleteMessage %s/%s failed: %r", chat_id, message_id, exc)
        return DeleteOutcome(ok=False, error="Telegram bilan bog'lanib bo'lmadi")

    if body.get("ok"):
        return DeleteOutcome(ok=True)

    description = str(body.get("description") or "").lower()
    if any(phrase in description for phrase in _ALREADY_GONE):
        return DeleteOutcome(ok=True, already_gone=True)

    for phrase, message in _REASONS.items():
        if phrase in description:
            return DeleteOutcome(ok=False, error=message)

    logger.info("deleteMessage %s/%s refused: %s", chat_id, message_id, description)
    return DeleteOutcome(ok=False, error=body.get("description") or "Telegram rad etdi")
