from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import RequestStatus
from afu_shared.models import Employee, Rating, Request, RequestAssignee
from app.deps import get_db
from app.schemas.rating import StaffRatingSummary

router = APIRouter(prefix="/ratings", tags=["ratings"])


@router.get("/leaderboard", response_model=list[StaffRatingSummary])
async def leaderboard(session: AsyncSession = Depends(get_db)) -> list[StaffRatingSummary]:
    # Counted through request_assignees: a job two people did together counts for both of
    # them. Reading Request.assigned_to_employee_id would credit only the primary and make
    # a colleague's contribution vanish from the board.
    completed_counts = dict(
        (
            await session.execute(
                select(RequestAssignee.employee_id, func.count())
                .join(Request, Request.id == RequestAssignee.request_id)
                .where(Request.status == RequestStatus.COMPLETED.value)
                .group_by(RequestAssignee.employee_id)
            )
        ).all()
    )

    rating_rows = (
        await session.execute(
            select(Rating.rated_employee_id, func.avg(Rating.score), func.count())
            .group_by(Rating.rated_employee_id)
        )
    ).all()
    rating_map = {employee_id: (avg, count) for employee_id, avg, count in rating_rows}

    staff = (
        await session.execute(select(Employee).where(Employee.is_rtm_staff.is_(True)))
    ).scalars()

    summaries = []
    for s in staff:
        avg, count = rating_map.get(s.id, (None, 0))
        summaries.append(
            StaffRatingSummary(
                employee_id=s.id,
                full_name=s.full_name,
                completed_count=completed_counts.get(s.id, 0),
                average_score=round(avg, 2) if avg is not None else None,
                rating_count=count,
            )
        )

    summaries.sort(key=lambda x: (x.average_score is None, -(x.average_score or 0), -x.completed_count))
    return summaries


@router.get("/staff/{employee_id}", response_model=StaffRatingSummary)
async def staff_rating(employee_id: int, session: AsyncSession = Depends(get_db)) -> StaffRatingSummary:
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    completed_count = (
        await session.execute(
            select(func.count())
            .select_from(RequestAssignee)
            .join(Request, Request.id == RequestAssignee.request_id)
            .where(
                RequestAssignee.employee_id == employee_id,
                Request.status == RequestStatus.COMPLETED.value,
            )
        )
    ).scalar_one()

    avg, count = (
        await session.execute(
            select(func.avg(Rating.score), func.count()).where(Rating.rated_employee_id == employee_id)
        )
    ).one()

    return StaffRatingSummary(
        employee_id=employee.id,
        full_name=employee.full_name,
        completed_count=completed_count,
        average_score=round(avg, 2) if avg is not None else None,
        rating_count=count,
    )
