from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import MessageVisibility, RequestSource, RequestStatus
from afu_shared.models import Employee, Rating, Request, RequestAttachment, RequestMessage, RequestStatusHistory, User
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


async def _get_request_or_404(session: AsyncSession, request_id: int) -> Request:
    request = await session.get(Request, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return request


def _check_can_view(request: Request, caller: User | Employee) -> None:
    if isinstance(caller, User):
        return
    if request.requester_employee_id == caller.id:
        return
    if caller.is_rtm_staff:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")


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
    await session.refresh(request)
    return RequestResponse.from_request(request)


@router.get("", response_model=list[RequestResponse])
async def list_requests(
    status_filter: str | None = None,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> list[RequestResponse]:
    stmt = select(Request)

    if isinstance(caller, Employee):
        if caller.is_rtm_staff:
            stmt = stmt.where(
                or_(
                    Request.requester_employee_id == caller.id,
                    Request.assigned_to_employee_id == caller.id,
                )
            )
        else:
            stmt = stmt.where(Request.requester_employee_id == caller.id)

    if status_filter:
        stmt = stmt.where(Request.status == status_filter)

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
    _check_can_view(request, caller)
    return RequestResponse.from_request(request)


@router.patch("/{request_id}/assign", response_model=RequestResponse)
async def assign_request(
    request_id: int,
    payload: RequestAssign,
    admin: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> RequestResponse:
    if not isinstance(admin, User):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    request = await _get_request_or_404(session, request_id)
    staff = await session.get(Employee, payload.assigned_to_employee_id)
    if not staff or not staff.is_rtm_staff:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not an RTM staff employee")

    old_status = request.status
    request.assigned_to_employee_id = staff.id
    request.assigned_by_user_id = admin.id
    request.assigned_at = datetime.now(timezone.utc)
    request.deadline_at = payload.deadline_at
    if request.status == RequestStatus.NEW.value:
        request.status = RequestStatus.ASSIGNED.value

    session.add(
        RequestStatusHistory(
            request_id=request.id,
            from_status=old_status,
            to_status=request.status,
            changed_by_user_id=admin.id,
            note=f"Tayinlandi: {staff.full_name}",
        )
    )
    await session.flush()
    await session.refresh(request)
    return RequestResponse.from_request(request)


@router.patch("/{request_id}/status", response_model=RequestResponse)
async def update_status(
    request_id: int,
    payload: RequestStatusUpdate,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> RequestResponse:
    request = await _get_request_or_404(session, request_id)

    if isinstance(caller, Employee):
        if not caller.is_rtm_staff or request.assigned_to_employee_id != caller.id:
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

    if isinstance(caller, Employee) and request.assigned_to_employee_id != caller.id:
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

    pool = await get_arq_pool()
    await pool.enqueue_job("send_completion_notification", request.id)

    await session.refresh(request)
    return RequestResponse.from_request(request)


@router.get("/{request_id}/messages", response_model=list[RequestMessageResponse])
async def list_messages(
    request_id: int,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> list[RequestMessage]:
    request = await _get_request_or_404(session, request_id)
    _check_can_view(request, caller)

    stmt = select(RequestMessage).where(RequestMessage.request_id == request_id)
    if isinstance(caller, Employee) and not caller.is_rtm_staff:
        stmt = stmt.where(RequestMessage.visibility == MessageVisibility.TO_REQUESTER.value)
    stmt = stmt.order_by(RequestMessage.created_at)

    result = await session.execute(stmt)
    return list(result.scalars())


@router.post("/{request_id}/messages", response_model=RequestMessageResponse)
async def post_message(
    request_id: int,
    payload: RequestMessageCreate,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> RequestMessage:
    request = await _get_request_or_404(session, request_id)
    _check_can_view(request, caller)

    if isinstance(caller, Employee) and not caller.is_rtm_staff and payload.visibility != MessageVisibility.TO_REQUESTER.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    message = RequestMessage(
        request_id=request_id,
        author_employee_id=caller.id if isinstance(caller, Employee) else None,
        author_user_id=caller.id if isinstance(caller, User) else None,
        visibility=payload.visibility,
        body=payload.body,
    )
    session.add(message)
    await session.flush()
    await session.refresh(message)
    return message


@router.get("/{request_id}/attachments/{attachment_id}")
async def download_attachment(
    request_id: int,
    attachment_id: int,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
):
    request = await _get_request_or_404(session, request_id)
    _check_can_view(request, caller)

    attachment = await session.get(RequestAttachment, attachment_id)
    if not attachment or attachment.request_id != request_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    full_path = f"{settings.storage_root}/{attachment.file_path}"
    return FileResponse(full_path, filename=attachment.original_filename or "file")


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
    if not request.assigned_to_employee_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request has no assignee")

    existing = (
        await session.execute(select(Rating).where(Rating.request_id == request_id))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already rated")

    rating = Rating(
        request_id=request_id,
        rated_employee_id=request.assigned_to_employee_id,
        rated_by_employee_id=caller.id,
        score=payload.score,
        comment=payload.comment,
    )
    session.add(rating)
    await session.flush()
    await session.refresh(rating)
    return rating


@router.get("/{request_id}/attachments-list", response_model=list[RequestAttachmentResponse])
async def list_attachments(
    request_id: int,
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> list[RequestAttachment]:
    request = await _get_request_or_404(session, request_id)
    _check_can_view(request, caller)
    result = await session.execute(
        select(RequestAttachment).where(RequestAttachment.request_id == request_id)
    )
    return list(result.scalars())
