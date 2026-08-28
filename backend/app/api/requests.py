import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import delete as sql_delete
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.assignments import assignee_ids, set_assignees
from afu_shared.activity import record_for
from afu_shared.enums import AttachmentKind, MessageVisibility, RequestSource, RequestStatus
from afu_shared.models import (
    Employee,
    InventoryMovement,
    Rating,
    Request,
    RequestAssignee,
    RequestAttachment,
    RequestGroupPost,
    RequestMessage,
    RequestStatusHistory,
    User,
)
from afu_shared.richtext import html_to_text, sanitize_html
from afu_shared.settings import settings
from app.arq_pool import get_arq_pool
from app.deps import get_admin_actor, get_current_caller, get_db
from app.downloads import serve_headers
from app.schemas.rating import RatingCreate, RatingResponse
from app.schemas.request import (
    RequestAssign,
    RequestAttachmentResponse,
    RequestBulkDelete,
    RequestBulkDeleteResult,
    RequestComplete,
    RequestCreate,
    RequestMessageCreate,
    RequestMessageResponse,
    RequestResponse,
    RequestReturn,
    RequestStatusUpdate,
)

router = APIRouter(prefix="/requests", tags=["requests"])

#: Kept in step with ``client_max_body_size`` in deploy/frontend-nginx.conf — nginx would
#: otherwise reject the request before FastAPI ever sees it, and the user would get a bare
#: 413 page instead of a readable message.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

#: How many requests one bulk delete may take. High enough to clear a screenful of test
#: data in one press, low enough that a mistyped selection cannot empty the queue.
BULK_DELETE_LIMIT = 200


async def _get_request_or_404(session: AsyncSession, request_id: int) -> Request:
    request = await session.get(Request, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return request


async def _check_can_view(
    session: AsyncSession, request: Request, caller: User | Employee
) -> None:
    """Who may read one request, its thread and its files.

    RTM staff used to be able to read *every* request by id. Membership is the rule now: a
    staffer sees the jobs they were given or picked up, plus anything they reported
    themselves, and nothing else. Boshliq and Admin keep the full view because handing work
    out is impossible without reading it first — that is the whole of their role.
    """
    if isinstance(caller, User):
        return
    if request.requester_employee_id == caller.id:
        return
    if caller.can_manage_assignments:
        return
    if caller.is_rtm_staff and caller.id in await assignee_ids(session, request.id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Bu murojaat sizga biriktirilmagan",
    )


async def _resolve_staff(session: AsyncSession, employee_ids: list[int]) -> list[Employee]:
    """The employees behind ``employee_ids``, refusing anyone who is not RTM staff."""
    staff = []
    for employee_id in employee_ids:
        candidate = await session.get(Employee, employee_id)
        if not candidate or not candidate.is_rtm_staff:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Not an RTM staff employee"
            )
        staff.append(candidate)
    return staff


@router.post("", response_model=RequestResponse)
async def create_request(
    payload: RequestCreate,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> RequestResponse:
    if not isinstance(caller, Employee):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only employees can create requests")

    # The markup is re-sanitized here rather than trusted from the editor: the browser copy
    # is a convenience for whoever is typing, and a hand-written POST never runs it at all.
    description_html = sanitize_html(payload.description_html)
    # Derived, never taken from the client: ``description`` is what every Telegram surface
    # prints, and letting the two arrive independently is how they come to disagree.
    description = html_to_text(description_html) or payload.description.strip()
    if not description:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Tavsif bo'sh bo'lishi mumkin emas"
        )

    # De-duplicated with the order kept: the first name picked is the one who leads the job.
    employee_ids = list(dict.fromkeys(payload.assigned_to_employee_ids))
    if employee_ids and not caller.can_manage_assignments:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faqat Boshliq yoki Admin tayinlay oladi",
        )
    staff = await _resolve_staff(session, employee_ids)

    request = Request(
        requester_employee_id=caller.id,
        category_slug=payload.category_slug,
        description=description,
        description_html=description_html or None,
        status=RequestStatus.NEW.value,
        source=RequestSource.WEB.value,
        # A deadline is a promise made on RTM's behalf, so only somebody who may hand work
        # out can make one. Set here rather than after the flush so that the very first
        # group card already carries it.
        deadline_at=payload.deadline_at if caller.can_manage_assignments else None,
    )
    session.add(request)
    await session.flush()
    session.add(
        RequestStatusHistory(
            request_id=request.id,
            from_status=None,
            to_status=RequestStatus.NEW.value,
            changed_by_employee_id=caller.id,
        )
    )
    await session.flush()

    if employee_ids:
        # Before the card is published, so the group sees "assigned to X" rather than a
        # request that appears unclaimed and is silently taken a second later.
        # set_assignees owns the assignee table, the primary column, the status and the
        # new-to-assigned history row, so nothing here writes those directly.
        await set_assignees(session, request, employee_ids)
        await session.flush()

    await session.commit()

    await record_for(
        session, caller, action="request.create", target=request.display_number
    )
    if staff:
        await record_for(
            session,
            caller,
            action="request.assign",
            target=request.display_number,
            detail=", ".join(s.full_name for s in staff),
        )
    await session.commit()

    pool = await get_arq_pool()
    await pool.enqueue_job("publish_request_card", request.id)
    for employee in staff:
        await pool.enqueue_job("notify_request_assigned", request.id, employee.id)

    await session.refresh(request)
    return RequestResponse.from_request(request)


@router.get("", response_model=list[RequestResponse])
async def list_requests(
    status_filter: str | None = None,
    category_slug: str | None = None,
    assignee_employee_id: int | None = None,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> list[RequestResponse]:
    """Everything the caller is allowed to see, narrowed by the filters they asked for.

    The scope is decided here and not in the query string: a filter is a convenience, and
    dropping it must never widen what somebody can read.
    """
    stmt = select(Request)

    # Boshliq and Admin see the whole queue — they are the ones who decide where a request
    # goes, and cannot do that from a list of their own work.
    if isinstance(caller, Employee) and not caller.can_manage_assignments:
        if caller.is_rtm_staff:
            stmt = stmt.where(
                or_(
                    Request.requester_employee_id == caller.id,
                    # Membership, not the primary column: a colleague who joined a job
                    # would otherwise not find it in their own list.
                    Request.assignees.any(RequestAssignee.employee_id == caller.id),
                )
            )
        else:
            stmt = stmt.where(Request.requester_employee_id == caller.id)

    if status_filter:
        stmt = stmt.where(Request.status == status_filter)
    else:
        # A returned request is not work, it is a rejection: leaving it in the default list
        # would put something nobody is going to do at the top of the queue every morning.
        # Asking for it by name (status_filter=returned) is the way to see them.
        stmt = stmt.where(Request.status != RequestStatus.RETURNED.value)
    if category_slug:
        stmt = stmt.where(Request.category_slug == category_slug)
    if assignee_employee_id is not None:
        stmt = stmt.where(
            Request.assignees.any(RequestAssignee.employee_id == assignee_employee_id)
        )

    stmt = stmt.order_by(Request.created_at.desc()).limit(200)
    result = await session.execute(stmt)
    return [RequestResponse.from_request(r) for r in result.scalars()]


@router.get("/{request_id}", response_model=RequestResponse)
async def get_request(
    request_id: int,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> RequestResponse:
    request = await _get_request_or_404(session, request_id)
    await _check_can_view(session, request, caller)
    return RequestResponse.from_request(request)


@router.post("/{request_id}/assign", response_model=RequestResponse)
async def assign_request(
    request_id: int,
    payload: RequestAssign,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> RequestResponse:
    # Panel admins, and employees marked Boshliq or Admin. Deciding who does the work — and
    # taking somebody off a job — is the one thing those two roles exist for, and the whole
    # point is that it does not have to wait for whoever holds the panel password.
    if isinstance(caller, Employee) and not caller.can_manage_assignments:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faqat Boshliq yoki Admin tayinlay oladi",
        )
    admin_user_id = caller.id if isinstance(caller, User) else None

    request = await _get_request_or_404(session, request_id)
    employee_ids = payload.employee_ids()
    if not employee_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Kamida bitta xodim tanlang"
        )

    staff = await _resolve_staff(session, employee_ids)

    previously = set(await assignee_ids(session, request.id))

    old_status = request.status
    if request.deadline_at != payload.deadline_at:
        # A new deadline is a new promise, so it becomes warnable again. Leaving the old
        # mark in place would mean an extended deadline could never be missed a second time.
        request.overdue_notified_at = None
    request.deadline_at = payload.deadline_at
    # set_assignees owns the assignee table, the primary column and the new/assigned
    # transition, so nothing here touches those directly.
    await set_assignees(session, request, employee_ids, assigned_by_user_id=admin_user_id)

    session.add(
        RequestStatusHistory(
            request_id=request.id,
            from_status=old_status,
            to_status=request.status,
            changed_by_user_id=admin_user_id,
            changed_by_employee_id=caller.id if isinstance(caller, Employee) else None,
            note="Tayinlandi: " + ", ".join(s.full_name for s in staff),
        )
    )
    await record_for(
        session,
        caller,
        action="request.assign",
        target=request.display_number,
        detail=", ".join(s.full_name for s in staff),
    )
    await session.flush()

    # Commit before the jobs are queued: the worker reads the request back from the database
    # in its own session, and a job that overtakes this transaction would find the old
    # assignees (or none at all).
    await session.commit()
    pool = await get_arq_pool()
    # Only people who were not already on it — re-saving the form with one name added must
    # not re-brief everybody who has been working on it for an hour.
    for employee in staff:
        if employee.id not in previously:
            await pool.enqueue_job("notify_request_assigned", request.id, employee.id)
    await pool.enqueue_job(
        "refresh_request_cards",
        request.id,
        "📌 <b>{}</b> — {} ga tayinlandi.".format(
            request.display_number, ", ".join(s.full_name for s in staff)
        ),
    )

    await session.refresh(request)
    return RequestResponse.from_request(request)


@router.post("/{request_id}/status", response_model=RequestResponse)
async def update_status(
    request_id: int,
    payload: RequestStatusUpdate,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> RequestResponse:
    request = await _get_request_or_404(session, request_id)

    if isinstance(caller, Employee):
        if not caller.is_rtm_staff or caller.id not in await assignee_ids(session, request_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    if payload.status not in {s.value for s in RequestStatus}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    # Returning has its own endpoint because it is more than a status: it records the
    # reason and tells the reporter. Reached through here it would do neither, and leave a
    # request sitting in "returned" that nobody was ever told about.
    if payload.status == RequestStatus.RETURNED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Murojaatni qaytarish uchun «Qaytarib yuborish» amalidan foydalaning",
        )

    old_status = request.status
    request.status = payload.status
    session.add(
        RequestStatusHistory(
            request_id=request.id,
            from_status=old_status,
            to_status=payload.status,
            changed_by_employee_id=caller.id if isinstance(caller, Employee) else None,
            changed_by_user_id=caller.id if isinstance(caller, User) else None,
            note=payload.note,
        )
    )
    await session.flush()
    await session.refresh(request)
    return RequestResponse.from_request(request)


@router.post("/{request_id}/complete", response_model=RequestResponse)
async def complete_request(
    request_id: int,
    payload: RequestComplete,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> RequestResponse:
    request = await _get_request_or_404(session, request_id)

    if isinstance(caller, Employee) and caller.id not in await assignee_ids(session, request_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    old_status = request.status
    request.status = RequestStatus.COMPLETED.value
    request.completed_at = datetime.now(timezone.utc)
    request.completion_note = payload.completion_note

    session.add(
        RequestStatusHistory(
            request_id=request.id,
            from_status=old_status,
            to_status=request.status,
            changed_by_employee_id=caller.id if isinstance(caller, Employee) else None,
            changed_by_user_id=caller.id if isinstance(caller, User) else None,
        )
    )
    await record_for(
        session, caller, action="request.complete", target=request.display_number
    )
    await session.flush()
    await session.commit()

    pool = await get_arq_pool()
    await pool.enqueue_job("send_completion_notification", request.id)
    await pool.enqueue_job(
        "refresh_request_cards",
        request.id,
        f"✅ <b>{request.display_number}</b> bajarildi.",
    )

    await session.refresh(request)
    return RequestResponse.from_request(request)


@router.post("/{request_id}/return", response_model=RequestResponse)
async def return_request(
    request_id: int,
    payload: RequestReturn,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> RequestResponse:
    """Send a wrongly filed request back to whoever reported it.

    Not the same act as cancelling. Cancelling closes work RTM took on; returning says the
    request never should have been in the queue — wrong department, too little to act on, a
    duplicate — so it leaves the working list entirely and the reporter is told why.

    Assignees are deliberately left on the row. Somebody may well have picked this up in the
    group before anyone read it properly, and erasing that would hide who was holding it
    when it went back; the staff screens key off the status, so it drops out of their queue
    regardless.
    """
    if isinstance(caller, Employee) and not caller.can_manage_assignments:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faqat Boshliq yoki Admin murojaatni qaytara oladi",
        )

    request = await _get_request_or_404(session, request_id)

    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Qaytarish sababini yozing — murojaatchi shu matnni oladi",
        )
    if request.status == RequestStatus.RETURNED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Bu murojaat allaqachon qaytarilgan"
        )
    if request.status == RequestStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bajarilgan murojaatni qaytarib bo'lmaydi",
        )

    old_status = request.status
    request.status = RequestStatus.RETURNED.value
    request.returned_at = datetime.now(timezone.utc)
    request.return_reason = reason
    # It is not parked on a part any more, and it is not late any more either.
    request.waiting_until = None
    request.waiting_reason = None
    request.overdue_notified_at = None

    session.add(
        RequestStatusHistory(
            request_id=request.id,
            from_status=old_status,
            to_status=request.status,
            changed_by_employee_id=caller.id if isinstance(caller, Employee) else None,
            changed_by_user_id=caller.id if isinstance(caller, User) else None,
            note=reason,
        )
    )
    await record_for(
        session, caller, action="request.return", target=request.display_number, detail=reason
    )
    await session.flush()
    # Commit before queueing: the worker re-reads the request in its own session and would
    # otherwise redraw the card and write the notification from the pre-return state.
    await session.commit()

    pool = await get_arq_pool()
    await pool.enqueue_job("notify_request_returned", request.id)
    await pool.enqueue_job(
        "refresh_request_cards",
        request.id,
        f"🚫 <b>{request.display_number}</b> qaytarib yuborildi. Sabab: {reason}",
    )

    await session.refresh(request)
    return RequestResponse.from_request(request)


async def _purge_request(session: AsyncSession, request: Request) -> list[tuple[int, int]]:
    """Erase one request and everything hanging off it. Returns its group card posts.

    Deletion is spelled out row by row rather than left to the database, because the
    foreign keys here have no ``ON DELETE`` behaviour and Postgres would simply refuse.
    The order is the dependency order: attachments point at messages, so they go first.

    Files on disk go with the rows that name them: a deleted request that leaves its photos
    behind is a storage leak nobody ever notices.

    **Inventory movements are the one exception** — they are kept and merely unlinked. A
    part taken out of stock actually left the store, so deleting the record would make the
    running total wrong for ever. A movement whose job is no longer named is a far smaller
    problem than a stock figure that no longer matches the shelf.
    """
    request_id = request.id

    posts = list(
        (
            await session.execute(
                select(RequestGroupPost).where(RequestGroupPost.request_id == request_id)
            )
        ).scalars()
    )
    card_posts = [(post.chat_id, post.message_id) for post in posts]

    attachments = list(
        (
            await session.execute(
                select(RequestAttachment).where(RequestAttachment.request_id == request_id)
            )
        ).scalars()
    )
    storage_root = Path(settings.storage_root)
    for attachment in attachments:
        if attachment.file_path:
            (storage_root / attachment.file_path).unlink(missing_ok=True)
    # The request's own folder, so a purge of test data does not leave a few hundred empty
    # directories behind.
    shutil.rmtree(storage_root / "requests" / str(request_id), ignore_errors=True)

    await session.execute(
        update(InventoryMovement)
        .where(InventoryMovement.request_id == request_id)
        .values(request_id=None)
    )

    for model in (
        Rating,
        RequestAttachment,
        RequestMessage,
        RequestAssignee,
        RequestStatusHistory,
        RequestGroupPost,
    ):
        await session.execute(sql_delete(model).where(model.request_id == request_id))

    await session.delete(request)
    await session.flush()
    return card_posts


# POST, not DELETE: the production reverse proxy allows GET, POST and HEAD only, so a
# DELETE would be refused with a 405 by a component this repository cannot configure.
@router.post("/{request_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_request(
    request_id: int,
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Remove a request completely. Admin only, at any status.

    Deliberately not restricted to open requests: the reason this exists is a queue full of
    requests filed while testing, and those are exactly the ones that were carried through
    to "completed" to see what completing them did. Returning or cancelling leaves the row
    in the statistics, which is the opposite of what is wanted here.

    Not offered to Boshliq. Handing work out is a supervisor's job; making the record of it
    disappear is not.
    """
    request = await _get_request_or_404(session, request_id)
    display_number = request.display_number

    card_posts = await _purge_request(session, request)
    await record_for(session, actor, action="request.delete", target=display_number)
    await session.commit()

    # After the commit: the card is gone from the database either way, and a Telegram
    # failure must not roll back the deletion.
    pool = await get_arq_pool()
    for chat_id, message_id in card_posts:
        await pool.enqueue_job("delete_telegram_message", chat_id, message_id)


@router.post("/bulk-delete", response_model=RequestBulkDeleteResult)
async def bulk_delete_requests(
    payload: RequestBulkDelete,
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> RequestBulkDeleteResult:
    """Delete several requests at once — clearing out test data, one screen at a time.

    Ids that no longer exist are reported rather than raising: two administrators tidying
    the same list would otherwise take turns failing on rows the other one just removed.
    """
    request_ids = list(dict.fromkeys(payload.request_ids))
    if not request_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Hech qanday murojaat tanlanmadi"
        )
    if len(request_ids) > BULK_DELETE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bir vaqtda {BULK_DELETE_LIMIT} tagacha murojaatni o'chirish mumkin",
        )

    deleted: list[str] = []
    missing: list[int] = []
    card_posts: list[tuple[int, int]] = []
    for request_id in request_ids:
        request = await session.get(Request, request_id)
        if request is None:
            missing.append(request_id)
            continue
        deleted.append(request.display_number)
        card_posts.extend(await _purge_request(session, request))

    if deleted:
        await record_for(
            session,
            actor,
            action="request.delete",
            target=f"{len(deleted)} ta murojaat",
            detail=", ".join(deleted),
        )
    await session.commit()

    pool = await get_arq_pool()
    for chat_id, message_id in card_posts:
        await pool.enqueue_job("delete_telegram_message", chat_id, message_id)

    return RequestBulkDeleteResult(deleted=len(deleted), missing=missing)


@router.get("/{request_id}/messages", response_model=list[RequestMessageResponse])
async def list_messages(
    request_id: int,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> list[RequestMessageResponse]:
    request = await _get_request_or_404(session, request_id)
    await _check_can_view(session, request, caller)

    stmt = (
        select(RequestMessage, Employee)
        .outerjoin(Employee, RequestMessage.author_employee_id == Employee.id)
        .where(RequestMessage.request_id == request_id)
    )
    if isinstance(caller, Employee) and not caller.is_rtm_staff:
        stmt = stmt.where(RequestMessage.visibility == MessageVisibility.TO_REQUESTER.value)
    stmt = stmt.order_by(RequestMessage.created_at)

    return [
        RequestMessageResponse.from_message(
            message, author_name=author.full_name if author else None
        )
        for message, author in (await session.execute(stmt)).all()
    ]


@router.post("/{request_id}/messages", response_model=RequestMessageResponse)
async def post_message(
    request_id: int,
    payload: RequestMessageCreate,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> RequestMessageResponse:
    request = await _get_request_or_404(session, request_id)
    await _check_can_view(session, request, caller)

    if isinstance(caller, Employee) and not caller.is_rtm_staff and payload.visibility != MessageVisibility.TO_REQUESTER.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    body = payload.body.strip() or None
    if body is None and not payload.attachment_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Xabar bo'sh bo'lishi mumkin emas"
        )

    message = RequestMessage(
        request_id=request_id,
        author_employee_id=caller.id if isinstance(caller, Employee) else None,
        author_user_id=caller.id if isinstance(caller, User) else None,
        visibility=payload.visibility,
        body=body,
    )
    session.add(message)
    await session.flush()

    owned: list[RequestAttachment] = []
    if payload.attachment_ids:
        # Only unclaimed files on this same request, so one message cannot steal another's
        # attachments by guessing ids.
        owned = list(
            (
                await session.execute(
                    select(RequestAttachment).where(
                        RequestAttachment.id.in_(payload.attachment_ids),
                        RequestAttachment.request_id == request_id,
                        RequestAttachment.message_id.is_(None),
                    )
                )
            ).scalars()
        )
        for attachment in owned:
            attachment.message_id = message.id
        await session.flush()

    await session.commit()

    # A message written on the web has to reach the other party's Telegram, exactly like
    # one written in the bot. Without this the two interfaces looked identical but only one
    # of them actually delivered anything.
    # None for an admin: they have no employee row, and the worker reads that as
    # "written by RTM", which is the right direction for them.
    pool = await get_arq_pool()
    await pool.enqueue_job(
        "notify_request_message",
        request_id,
        caller.id if isinstance(caller, Employee) else None,
        message.id,
    )

    await session.refresh(message)
    author_name = caller.full_name if isinstance(caller, Employee) else None
    return RequestMessageResponse.from_message(
        message, author_name=author_name, attachments=owned
    )


@router.get("/{request_id}/attachments/{attachment_id}")
async def download_attachment(
    request_id: int,
    attachment_id: int,
    download: bool = False,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
):
    """Serve one attachment.

    Inline by default so the browser can play it in place — a voice reply is only useful
    if it plays where it was written, and forcing every file through a download would make
    the web thread strictly worse than the Telegram one. ``?download=1`` restores the
    save-to-disk behaviour for anything the reader wants to keep.
    """
    request = await _get_request_or_404(session, request_id)
    await _check_can_view(session, request, caller)

    attachment = await session.get(RequestAttachment, attachment_id)
    if not attachment or attachment.request_id != request_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    if not attachment.file_path:
        # Over the Bot API download ceiling: it lives in Telegram only.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File is only available in Telegram"
        )

    full_path = Path(settings.storage_root) / attachment.file_path
    if not full_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk")

    name = attachment.original_filename or full_path.name
    # The stored content type is whatever the uploader's browser claimed, so the decision
    # about what may render inline is made by us, not by them. See app/downloads.py.
    media_type, headers = serve_headers(attachment.content_type, name, want_download=download)
    return FileResponse(full_path, media_type=media_type, headers=headers)


@router.post("/{request_id}/attachments", response_model=RequestAttachmentResponse)
async def upload_attachment(
    request_id: int,
    file: UploadFile = File(...),
    message_id: int | None = Form(default=None),
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> RequestAttachmentResponse:
    """Attach a file from the web interface."""
    request = await _get_request_or_404(session, request_id)
    await _check_can_view(session, request, caller)
    if not isinstance(caller, Employee):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only employees can attach files"
        )

    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Fayl hajmi {MAX_UPLOAD_BYTES // (1024 * 1024)} MB dan oshmasligi kerak",
        )

    if message_id is not None:
        owner = await session.get(RequestMessage, message_id)
        if owner is None or owner.request_id != request_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown message"
            )

    suffix = Path(file.filename or "").suffix.lower()[:8] or ".bin"
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    target_dir = Path(settings.storage_root) / "requests" / str(request_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / stored_name).write_bytes(payload)

    attachment = RequestAttachment(
        request_id=request_id,
        message_id=message_id,
        uploaded_by_employee_id=caller.id,
        kind=_kind_for(file.content_type),
        file_path=f"requests/{request_id}/{stored_name}",
        original_filename=file.filename,
        content_type=file.content_type,
        file_size=len(payload),
    )
    session.add(attachment)
    await session.flush()
    await session.refresh(attachment)

    if message_id is None:
        # A file on the request itself is part of what the group card shows. The web form
        # creates the request first and uploads afterwards, so the card is briefly posted
        # without its attachments — this is what fills them in.
        await session.commit()
        pool = await get_arq_pool()
        await pool.enqueue_job("refresh_request_cards", request_id)

    return RequestAttachmentResponse.from_attachment(attachment)


def _kind_for(content_type: str | None) -> str:
    """Classify a web upload the way Telegram would classify the same file."""
    mime = (content_type or "").lower()
    if mime.startswith("image/"):
        return AttachmentKind.PHOTO.value
    if mime.startswith("video/"):
        return AttachmentKind.VIDEO.value
    if mime.startswith("audio/"):
        return AttachmentKind.AUDIO.value
    return AttachmentKind.DOCUMENT.value


@router.post("/{request_id}/rating", response_model=RatingResponse)
async def rate_request(
    request_id: int,
    payload: RatingCreate,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> Rating:
    if not isinstance(caller, Employee):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the requester can rate")

    request = await _get_request_or_404(session, request_id)
    if request.requester_employee_id != caller.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your request")

    targets = await assignee_ids(session, request_id)
    if not targets:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request has no assignee")

    existing = (
        await session.execute(select(Rating).where(Rating.request_id == request_id).limit(1))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already rated")

    # One score, recorded against each person who worked on it. The requester rates the
    # service they received, not an individual — crediting only the primary assignee would
    # leave a colleague's work invisible in the leaderboard.
    ratings = [
        Rating(
            request_id=request_id,
            rated_employee_id=employee_id,
            rated_by_employee_id=caller.id,
            score=payload.score,
            comment=payload.comment,
        )
        for employee_id in targets
    ]
    session.add_all(ratings)
    await session.flush()
    await session.commit()

    pool = await get_arq_pool()
    await pool.enqueue_job("refresh_request_cards", request_id)

    await session.refresh(ratings[0])
    return ratings[0]


@router.get("/{request_id}/attachments-list", response_model=list[RequestAttachmentResponse])
async def list_attachments(
    request_id: int,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> list[RequestAttachmentResponse]:
    request = await _get_request_or_404(session, request_id)
    await _check_can_view(session, request, caller)

    stmt = (
        select(RequestAttachment)
        .where(RequestAttachment.request_id == request_id)
        .order_by(RequestAttachment.id)
    )
    if isinstance(caller, Employee) and not caller.is_rtm_staff:
        # Files hanging off an internal RTM note must not reach the requester. Mirrors the
        # visibility filter on the message list.
        stmt = stmt.outerjoin(
            RequestMessage, RequestAttachment.message_id == RequestMessage.id
        ).where(
            (RequestAttachment.message_id.is_(None))
            | (RequestMessage.visibility == MessageVisibility.TO_REQUESTER.value)
        )

    return [
        RequestAttachmentResponse.from_attachment(a)
        for a in (await session.execute(stmt)).scalars()
    ]
