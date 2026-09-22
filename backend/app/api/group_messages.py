"""What the bot is showing the RTM groups right now — and taking it back down.

Admin only, and deliberately so: this lists reporters' names and fault descriptions as they
appear in a shared chat, and every button on it removes something from a room full of
people.

**Two sources, one list.** A request card lives in ``request_group_posts``, because that row
is what lets the worker edit the card in place for the request's whole life. Everything else
the bot says to a group — the reply line when somebody takes a job, the overdue alarm, the
welcome notice, replayed files — lives in ``group_messages``. They are unioned here rather
than merged into one table, so that no Telegram message id is written down twice and the two
copies can never disagree about which message is which.

**A row is a claim, not a guarantee.** Anybody with rights in the group can delete anything
without telling us. A delete that Telegram answers with "no such message" is therefore
treated as success and the row is dropped: the panel's job was to make it gone.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from afu_shared.activity import record_for
from afu_shared.group_log import preview_of
from afu_shared.models import (
    Employee,
    GroupMessage,
    NotificationChat,
    Request,
    RequestGroupPost,
    User,
)
from app.deps import get_admin_actor, get_db
from app.schemas.group_message import (
    GroupChatResponse,
    GroupMessageDelete,
    GroupMessageDeleteResult,
    GroupMessageResponse,
)
from app.services.telegram import delete_message

router = APIRouter(prefix="/group-messages", tags=["group-messages"])

#: How many messages one screen shows. The two sources are merged and sorted in Python, so
#: this also bounds how much is read out of each of them.
PAGE_SIZE = 100

#: How many a single delete may take. One Telegram call per message, each with its own
#: timeout, all inside one request the admin is waiting on.
DELETE_LIMIT = 50

#: The kind string used for a request card. Not in ``group_log``'s list of kinds because
#: cards are not stored there — see the module docstring.
KIND_CARD = "card"


def _card_preview(request: Request | None) -> str | None:
    """What a card is about, in one line.

    The card's own text is not stored anywhere — it is rebuilt from the request every time
    the worker edits it — so this rebuilds the recognisable part rather than the whole thing.
    """
    if request is None:
        return None
    parts = [request.display_number]
    if request.category:
        parts.append(request.category.label_uz)
    if request.requester:
        parts.append(request.requester.full_name)
    body = preview_of(request.description) or ""
    head = " · ".join(parts)
    return f"{head} — {body}" if body else head


@router.get("/chats", response_model=list[GroupChatResponse])
async def list_chats(
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> list[GroupChatResponse]:
    """Every group the bot has been connected to, and how much of its output is in each.

    Inactive groups are listed too. The bot having been removed does not remove what it
    already posted, and a disconnected group is exactly the one somebody wants cleaned up.
    """
    now = datetime.now(timezone.utc)

    cards = dict(
        (
            await session.execute(
                select(RequestGroupPost.chat_id, func.count()).group_by(
                    RequestGroupPost.chat_id
                )
            )
        ).all()
    )
    others = dict(
        (
            await session.execute(
                select(GroupMessage.chat_id, func.count())
                .where(
                    or_(GroupMessage.expires_at.is_(None), GroupMessage.expires_at > now)
                )
                .group_by(GroupMessage.chat_id)
            )
        ).all()
    )

    chats = (
        await session.execute(
            select(NotificationChat).order_by(
                NotificationChat.is_active.desc(), NotificationChat.title
            )
        )
    ).scalars()

    return [
        GroupChatResponse(
            chat_id=chat.chat_id,
            title=chat.title,
            chat_type=chat.chat_type,
            is_active=chat.is_active,
            message_count=cards.get(chat.chat_id, 0) + others.get(chat.chat_id, 0),
        )
        for chat in chats
    ]


@router.get("", response_model=list[GroupMessageResponse])
async def list_group_messages(
    chat_id: int | None = None,
    kind: str | None = None,
    q: str | None = None,
    limit: int = PAGE_SIZE,
    offset: int = 0,
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> list[GroupMessageResponse]:
    """The bot's live output across the groups, newest first.

    Paged in Python over the two sources rather than in SQL over a UNION: the two tables
    have different shapes, the combined set is a few hundred rows at most, and a union view
    would have to be kept in step with both of them for the rest of the project's life.
    """
    now = datetime.now(timezone.utc)
    titles = dict(
        (await session.execute(select(NotificationChat.chat_id, NotificationChat.title))).all()
    )
    size = max(1, min(limit, PAGE_SIZE))
    # Read enough of each source that the merged, sorted result can still fill the page the
    # caller asked for, however lopsided the two are.
    window = size + max(0, offset)

    rows: list[GroupMessageResponse] = []

    if kind in (None, "", KIND_CARD):
        stmt = (
            select(RequestGroupPost)
            .join(Request, Request.id == RequestGroupPost.request_id)
            # The join makes the filters possible; the loader is what actually populates
            # ``post.request``. Without it, reading the attribute in an async session raises
            # rather than quietly issuing a second query.
            .options(selectinload(RequestGroupPost.request))
            .order_by(RequestGroupPost.created_at.desc())
        )
        if chat_id is not None:
            stmt = stmt.where(RequestGroupPost.chat_id == chat_id)
        if q:
            stmt = stmt.where(Request.description.ilike(f"%{q}%"))
        for post in (await session.execute(stmt.limit(window))).scalars():
            rows.append(
                GroupMessageResponse.build(
                    chat_id=post.chat_id,
                    chat_title=titles.get(post.chat_id),
                    message_id=post.message_id,
                    kind=KIND_CARD,
                    created_at=post.created_at,
                    request=post.request,
                    preview=_card_preview(post.request),
                )
            )

    if kind != KIND_CARD:
        stmt = select(GroupMessage).where(
            # Hidden once the bot's own countdown has run out, so the panel never offers to
            # delete something that is no longer on anybody's screen.
            or_(GroupMessage.expires_at.is_(None), GroupMessage.expires_at > now)
        )
        if chat_id is not None:
            stmt = stmt.where(GroupMessage.chat_id == chat_id)
        if kind:
            stmt = stmt.where(GroupMessage.kind == kind)
        if q:
            stmt = stmt.where(GroupMessage.preview.ilike(f"%{q}%"))
        stmt = stmt.order_by(GroupMessage.created_at.desc()).limit(window)
        for message in (await session.execute(stmt)).scalars():
            rows.append(
                GroupMessageResponse.build(
                    chat_id=message.chat_id,
                    chat_title=titles.get(message.chat_id),
                    message_id=message.message_id,
                    kind=message.kind,
                    created_at=message.created_at,
                    request=message.request,
                    preview=message.preview,
                    expires_at=message.expires_at,
                )
            )

    rows.sort(key=lambda row: row.created_at, reverse=True)
    return rows[offset : offset + size]


async def _delete_notes_of(
    session: AsyncSession, chat_id: int, request_id: int
) -> int:
    """Take down the reply lines a just-deleted card was holding up. Returns how many went.

    Only the ones we logged, and only in the same chat — the same card in another group is
    still standing and its notes still read correctly there.

    A note the bot never recorded (anything posted before this log existed) cannot be found
    from here; the panel's "delete by link" box is the way to those.
    """
    notes = list(
        (
            await session.execute(
                select(GroupMessage).where(
                    GroupMessage.chat_id == chat_id,
                    GroupMessage.request_id == request_id,
                )
            )
        ).scalars()
    )

    gone = 0
    for note in notes:
        outcome = await delete_message(chat_id, note.message_id)
        if not outcome.ok:
            # Left in the table on purpose: it is still in the group, so the panel should
            # keep offering it rather than pretend it dealt with it.
            continue
        await session.delete(note)
        gone += 1
    return gone


@router.post("/delete", response_model=GroupMessageDeleteResult)
async def delete_group_messages(
    payload: GroupMessageDelete,
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> GroupMessageDeleteResult:
    """Remove chosen messages from the group, and forget them here.

    POST rather than DELETE: the reverse proxy in front of this app forwards GET, POST and
    HEAD only, and several ids would not fit in a query string anyway.

    Telegram is called first and the row is dropped only once the message is actually gone.
    The other order would let a refused delete — the usual cause being a bot that is not a
    group administrator — quietly erase the panel's only record of a message that is still
    sitting in the chat.

    **Nothing here requires the message to be in our tables.** A ``(chat_id, message_id)``
    pair is all Telegram needs, and the pair is all this takes — which is what lets the
    panel clear out messages the bot posted before it started keeping a log. The rows are
    cleaned up if they happen to exist.

    Deleting a **card** also takes down the reply lines underneath it. Those notes quote the
    card, so once it is gone Telegram renders each of them under "Удалённое сообщение" —
    leftovers pointing at a message nobody can read, which is the exact mess this page was
    built to clear rather than to create.
    """
    refs = list(dict.fromkeys((m.chat_id, m.message_id) for m in payload.messages))
    if not refs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Hech qanday xabar tanlanmadi"
        )
    if len(refs) > DELETE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bir vaqtda {DELETE_LIMIT} tagacha xabarni o'chirish mumkin",
        )

    result = GroupMessageDeleteResult()
    for chat_id, message_id in refs:
        # Read before the delete: once the row is gone there is no way back to the request
        # whose notes have just been orphaned.
        card = (
            await session.execute(
                select(RequestGroupPost).where(
                    RequestGroupPost.chat_id == chat_id,
                    RequestGroupPost.message_id == message_id,
                )
            )
        ).scalar_one_or_none()

        outcome = await delete_message(chat_id, message_id)
        if not outcome.ok:
            result.failed.append(f"{message_id}: {outcome.error}")
            continue

        await session.execute(
            sql_delete(GroupMessage).where(
                GroupMessage.chat_id == chat_id, GroupMessage.message_id == message_id
            )
        )
        # The card's own row goes too. Without it the worker keeps editing a message that is
        # no longer there on every status change, and publish_request_card would never post
        # a replacement because it only posts where no row exists.
        await session.execute(
            sql_delete(RequestGroupPost).where(
                RequestGroupPost.chat_id == chat_id,
                RequestGroupPost.message_id == message_id,
            )
        )
        if outcome.already_gone:
            result.already_gone += 1
        else:
            result.deleted += 1

        if card is not None:
            result.cascaded += await _delete_notes_of(session, chat_id, card.request_id)

    if result.deleted or result.already_gone:
        await record_for(
            session,
            actor,
            action="group.message.delete",
            target=f"{result.deleted + result.already_gone} ta xabar",
            detail=", ".join(f"{chat}/{message}" for chat, message in refs),
        )
    await session.commit()
    return result
