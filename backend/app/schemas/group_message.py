"""What the bot currently has on screen in the RTM groups, and what came of deleting it."""

from datetime import datetime

from pydantic import BaseModel

from afu_shared.group_log import kind_label


class GroupChatResponse(BaseModel):
    """One registered group, with how much of the bot's output is sitting in it."""

    chat_id: int
    title: str | None = None
    chat_type: str | None = None
    is_active: bool = True
    #: Live messages the panel knows about in this chat — cards plus everything else.
    message_count: int = 0


class GroupMessageResponse(BaseModel):
    chat_id: int
    chat_title: str | None = None
    message_id: int
    #: ``card`` for a request card (from ``request_group_posts``), otherwise the
    #: ``group_messages`` kind. See ``app.api.group_messages`` for why there are two sources.
    kind: str
    kind_label: str
    request_id: int | None = None
    request_number: str | None = None
    request_status: str | None = None
    #: One plain line of what the message says.
    preview: str | None = None
    #: Deep link to the message inside Telegram. Only supergroups have one, and it only
    #: opens for somebody who is in the group — null rather than a link that goes nowhere.
    telegram_url: str | None = None
    #: Set only for the replayed files, which the bot deletes by itself when this passes.
    expires_at: datetime | None = None
    created_at: datetime

    @classmethod
    def build(
        cls,
        *,
        chat_id: int,
        chat_title: str | None,
        message_id: int,
        kind: str,
        created_at: datetime,
        request=None,
        preview: str | None = None,
        expires_at: datetime | None = None,
    ) -> "GroupMessageResponse":
        return cls(
            chat_id=chat_id,
            chat_title=chat_title,
            message_id=message_id,
            kind=kind,
            kind_label=kind_label(kind),
            request_id=request.id if request else None,
            request_number=request.display_number if request else None,
            request_status=request.status if request else None,
            preview=preview,
            telegram_url=telegram_message_url(chat_id, message_id),
            expires_at=expires_at,
            created_at=created_at,
        )


def telegram_message_url(chat_id: int, message_id: int) -> str | None:
    """``https://t.me/c/<internal id>/<message id>`` for a supergroup.

    Telegram's private-chat links drop the ``-100`` prefix supergroup ids carry. A basic
    group (ids that do not start with -100) has no such link at all, so this returns None
    rather than a URL that opens an error page.
    """
    text = str(chat_id)
    if not text.startswith("-100"):
        return None
    return f"https://t.me/c/{text[4:]}/{message_id}"


class GroupMessageRef(BaseModel):
    """One message to delete. The pair is the only identifier Telegram has."""

    chat_id: int
    message_id: int


class GroupMessageDelete(BaseModel):
    messages: list[GroupMessageRef] = []


class GroupMessageDeleteResult(BaseModel):
    #: Removed from the group by this call.
    deleted: int = 0
    #: Already gone before this call — a moderator got there first. Counted separately so
    #: the reply does not claim credit for them.
    already_gone: int = 0
    #: Refused by Telegram, each with the reason, so the fix ("make the bot an admin") is
    #: on screen instead of in a log file.
    failed: list[str] = []
