from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import RequestStatus
from afu_shared.models import Employee, Request, RequestAssignee, User
from app.deps import get_current_caller, get_db
from app.schemas.stats import MonthlyCount, StatsSummary

router = APIRouter(prefix="/stats", tags=["stats"])


def _scope_stmt(stmt, caller: User | Employee):
    if isinstance(caller, Employee):
        if caller.is_rtm_staff:
            # Through the assignee table so shared jobs count for everyone who worked on
            # them, not only for whoever picked the request up first.
            stmt = stmt.where(
                Request.assignees.any(RequestAssignee.employee_id == caller.id)
            )
        else:
            stmt = stmt.where(Request.requester_employee_id == caller.id)
    return stmt


@router.get("/summary", response_model=StatsSummary)
async def stats_summary(
    caller: User | Employee = Depends(get_current_caller), session: AsyncSession = Depends(get_db)
) -> StatsSummary:
    stmt = _scope_stmt(select(Request.status, func.count()).group_by(Request.status), caller)
    rows = dict((await session.execute(stmt)).all())

    return StatsSummary(
        total_requests=sum(rows.values()),
        new_count=rows.get(RequestStatus.NEW.value, 0),
        assigned_count=rows.get(RequestStatus.ASSIGNED.value, 0),
        in_progress_count=rows.get(RequestStatus.IN_PROGRESS.value, 0),
        completed_count=rows.get(RequestStatus.COMPLETED.value, 0),
        cancelled_count=rows.get(RequestStatus.CANCELLED.value, 0),
    )


@router.get("/completed-by-month", response_model=list[MonthlyCount])
async def completed_by_month(
    caller: User | Employee = Depends(get_current_caller), session: AsyncSession = Depends(get_db)
) -> list[MonthlyCount]:
    month_expr = func.to_char(Request.completed_at, "YYYY-MM")
    stmt = select(month_expr.label("month"), func.count()).where(
        Request.status == RequestStatus.COMPLETED.value
    )
    stmt = _scope_stmt(stmt, caller).group_by("month").order_by("month")

    rows = (await session.execute(stmt)).all()
    return [MonthlyCount(month=month, count=count) for month, count in rows]
