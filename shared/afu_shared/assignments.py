"""Who is working on a request.

The single owner of ``request_assignees`` **and** of ``Request.assigned_to_employee_id``.
Those two have to agree — the column is what lists and notifications read, the table is
what the group flow writes — and the only way to keep them agreeing is for one place to
change both. Nothing outside this module should assign or unassign.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import RequestStatus
from afu_shared.models import Employee, Request, RequestAssignee, RequestStatusHistory


#: Statuses a request can be picked up from. Finished or cancelled work is not up for grabs.
OPEN_FOR_PICKUP = (
    RequestStatus.NEW.value,
    RequestStatus.ASSIGNED.value,
    RequestStatus.IN_PROGRESS.value,
    RequestStatus.WAITING.value,
)


async def assignees_of(session: AsyncSession, request_id: int) -> list[RequestAssignee]:
    """Everyone on a request, the primary first, then in the order they joined."""
    return list(
        (
            await session.execute(
                select(RequestAssignee)
                .where(RequestAssignee.request_id == request_id)
                .order_by(RequestAssignee.is_primary.desc(), RequestAssignee.assigned_at)
            )
        ).scalars()
    )


async def assignee_ids(session: AsyncSession, request_id: int) -> list[int]:
    return [a.employee_id for a in await assignees_of(session, request_id)]


async def is_assigned(session: AsyncSession, request_id: int, employee_id: int) -> bool:
    return (
        await session.get(RequestAssignee, {"request_id": request_id, "employee_id": employee_id})
    ) is not None


async def add_assignee(
    session: AsyncSession,
    request: Request,
    employee: Employee,
    *,
    assigned_by_user_id: int | None = None,
) -> bool:
    """Put ``employee`` on ``request``. Returns False if they were already on it.

    The first person on a request becomes the primary and moves it out of ``new``; later
    joiners change nothing about its state, because a second pair of hands does not make a
    job more assigned than it already was.
    """
    existing = await session.get(
        RequestAssignee, {"request_id": request.id, "employee_id": employee.id}
    )
    if existing is not None:
        return False

    is_first = not await assignees_of(session, request.id)
    session.add(
        RequestAssignee(
            request_id=request.id,
            employee_id=employee.id,
            is_primary=is_first,
            assigned_by_user_id=assigned_by_user_id,
        )
    )

    if is_first:
        request.assigned_to_employee_id = employee.id
        request.assigned_by_user_id = assigned_by_user_id
        request.assigned_at = datetime.now(timezone.utc)
        if request.status == RequestStatus.NEW.value:
            _record_status(session, request, RequestStatus.ASSIGNED.value, employee)

    await session.flush()
    return True


async def remove_assignee(
    session: AsyncSession, request: Request, employee_id: int
) -> bool:
    """Take ``employee_id`` off ``request``. Returns False if they were not on it.

    Dropping the primary promotes whoever joined next rather than leaving the request
    ownerless, and a request nobody is left on goes back to ``new`` so it reappears as
    available instead of sitting in ``assigned`` with no assignee.
    """
    row = await session.get(
        RequestAssignee, {"request_id": request.id, "employee_id": employee_id}
    )
    if row is None:
        return False

    was_primary = row.is_primary
    await session.delete(row)
    await session.flush()

    remaining = await assignees_of(session, request.id)
    if not remaining:
        request.assigned_to_employee_id = None
        request.assigned_by_user_id = None
        request.assigned_at = None
        if request.status in (RequestStatus.ASSIGNED.value, RequestStatus.IN_PROGRESS.value):
            _record_status(session, request, RequestStatus.NEW.value, None)
    elif was_primary:
        successor = remaining[0]
        successor.is_primary = True
        request.assigned_to_employee_id = successor.employee_id

    await session.flush()
    return True


async def set_assignees(
    session: AsyncSession,
    request: Request,
    employee_ids: list[int],
    *,
    assigned_by_user_id: int | None = None,
) -> None:
    """Make the assignee set exactly ``employee_ids`` — the admin panel's operation.

    The first id given becomes the primary, so an admin choosing a lead gets the lead they
    chose rather than whoever the database returned first.

    Additions happen before removals, and that order matters: emptying the set first would
    send the request back to ``new`` on the way through, and a job that was already
    ``in_progress`` would come out the other side merely ``assigned`` — reassigning a live
    job would silently rewind its status.
    """
    for employee_id in employee_ids:
        employee = await session.get(Employee, employee_id)
        if employee is None:
            continue
        await add_assignee(
            session, request, employee, assigned_by_user_id=assigned_by_user_id
        )

    for row in list(await assignees_of(session, request.id)):
        if row.employee_id not in employee_ids:
            await remove_assignee(session, request, row.employee_id)

    if employee_ids:
        # Re-seat the primary: whoever was first before may still be flagged.
        for row in await assignees_of(session, request.id):
            row.is_primary = row.employee_id == employee_ids[0]
        request.assigned_to_employee_id = employee_ids[0]
        await session.flush()


def _record_status(
    session: AsyncSession, request: Request, to_status: str, employee: Employee | None
) -> None:
    previous = request.status
    request.status = to_status
    session.add(
        RequestStatusHistory(
            request_id=request.id,
            from_status=previous,
            to_status=to_status,
            changed_by_employee_id=employee.id if employee else None,
        )
    )
