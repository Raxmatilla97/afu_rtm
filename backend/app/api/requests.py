import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.assignments import assignee_ids, set_assignees
from afu_shared.enums import AttachmentKind, MessageVisibility, RequestSource, RequestStatus
from afu_shared.models import (
    Employee,
    Rating,
    Request,
    RequestAssignee,
    RequestAttachment,
    RequestMessage,
    RequestStatusHistory,
    User,
)
from afu_shared.settings import settings
from app.arq_pool import get_arq_pool
from app.deps import get_current_caller, get_db
from app.schemas.rating import RatingCreate, RatingResponse
from app.schemas.request import (
    RequestAssign,
    RequestAttachmentResponse,
    RequestComplete,
    RequestCreate,
    RequestMessageCreate,
    RequestMessageResponse,
    RequestResponse,
    RequestStatusUpdate,
)

router = APIRouter(prefix="/requests", tags=["requests"])

#: Kept in step with ``client_max_body_size`` in deploy/frontend-nginx.conf — nginx would
#: otherwise reject the request before FastAPI ever sees it, and the user would get a bare
#: 413 page instead of a readable message.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


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


@router.post("", response_model=RequestResponse)
async def create_request(
    payload: RequestCreate,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> RequestResponse:
    if not isinstance(caller, Employee):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only employees can create requests")

    request = Request(
        requester_employee_id=caller.id,
        category_slug=payload.category_slug,
        description=payload.description,
        status=RequestStatus.NEW.value,
        source=RequestSource.WEB.value,
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
    await session.commit()

    pool = await get_arq_pool()
    await pool.enqueue_job("publish_request_card", request.id)

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

    staff = []
    for employee_id in employee_ids:
        candidate = await session.get(Employee, employee_id)
        if not candidate or not candidate.is_rtm_staff:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Not an RTM staff employee"
            )
        staff.append(candidate)

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
    disposition = "attachment" if download else "inline"
    return FileResponse(
        full_path,
        media_type=attachment.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'{disposition}; filename="{_ascii_filename(name)}"'},
    )


def _ascii_filename(name: str) -> str:
    """Content-Disposition is a latin-1 header; a Cyrillic filename would break it."""
    return name.encode("ascii", "replace").decode("ascii").replace('"', "_")


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
