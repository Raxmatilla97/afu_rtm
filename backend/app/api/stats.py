from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import RequestStatus
from afu_shared.models import (
    Category,
    Employee,
    Rating,
    Request,
    RequestAssignee,
    User,
)
from app.deps import get_current_caller, get_db
from app.schemas.stats import (
    CategoryCount,
    MonthlyCount,
    MonthlyPoint,
    RatingBucket,
    ResolutionStats,
    StaffLoad,
    StatsOverview,
    StatsSummary,
)

router = APIRouter(prefix="/stats", tags=["stats"])

OPEN_STATUSES = (
    RequestStatus.NEW.value,
    RequestStatus.ASSIGNED.value,
    RequestStatus.IN_PROGRESS.value,
    RequestStatus.WAITING.value,
)

#: How far back the trend chart looks. A year fits on one axis without crowding and covers
#: the shape of a university year.
TREND_MONTHS = 12
#: Staff shown in the workload chart. Beyond this the bars get too thin to compare.
TOP_STAFF = 10


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
    return _summary_from(rows)


def _summary_from(rows: dict[str, int]) -> StatsSummary:
    return StatsSummary(
        total_requests=sum(rows.values()),
        new_count=rows.get(RequestStatus.NEW.value, 0),
        assigned_count=rows.get(RequestStatus.ASSIGNED.value, 0),
        in_progress_count=rows.get(RequestStatus.IN_PROGRESS.value, 0),
        waiting_count=rows.get(RequestStatus.WAITING.value, 0),
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


@router.get("/overview", response_model=StatsOverview)
async def stats_overview(
    caller: User | Employee = Depends(get_current_caller), session: AsyncSession = Depends(get_db)
) -> StatsOverview:
    """Every number the statistics page draws, in one round trip.

    One endpoint rather than seven: the page shows a single coherent picture, and seven
    independent fetches would let its panels disagree with each other while they arrive.

    Scoped exactly like the rest of the API — an admin sees the whole centre, an RTM
    staffer sees their own work, everybody else sees what they reported. The page does not
    have to know which; it draws what it is given.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=31 * TREND_MONTHS)

    status_rows = dict(
        (
            await session.execute(
                _scope_stmt(select(Request.status, func.count()), caller).group_by(Request.status)
            )
        ).all()
    )

    ratings, average_rating, rating_count = await _ratings(session, caller)

    open_overdue = (
        await session.execute(
            _scope_stmt(select(func.count()).select_from(Request), caller).where(
                Request.deadline_at.isnot(None),
                Request.deadline_at < now,
                Request.status.in_(OPEN_STATUSES),
            )
        )
    ).scalar_one()

    return StatsOverview(
        summary=_summary_from(status_rows),
        monthly=await _monthly(session, caller, since),
        by_category=await _by_category(session, caller),
        ratings=ratings,
        average_rating=average_rating,
        rating_count=rating_count,
        resolution=await _resolution(session, caller),
        staff_load=await _staff_load(session),
        open_overdue=open_overdue,
        unassigned=status_rows.get(RequestStatus.NEW.value, 0),
    )


async def _monthly(session: AsyncSession, caller, since: datetime) -> list[MonthlyPoint]:
    """Created and completed per month, aligned on one set of month keys.

    Two queries merged in Python rather than one clever SQL pivot: a month with
    completions but no new requests — or the reverse — must still appear, and a join would
    drop exactly those.
    """
    created_expr = func.to_char(Request.created_at, "YYYY-MM")
    created = dict(
        (
            await session.execute(
                _scope_stmt(select(created_expr.label("m"), func.count()), caller)
                .where(Request.created_at >= since)
                .group_by("m")
            )
        ).all()
    )

    completed_expr = func.to_char(Request.completed_at, "YYYY-MM")
    completed = dict(
        (
            await session.execute(
                _scope_stmt(select(completed_expr.label("m"), func.count()), caller)
                .where(
                    Request.status == RequestStatus.COMPLETED.value,
                    Request.completed_at >= since,
                )
                .group_by("m")
            )
        ).all()
    )

    months = sorted(set(created) | set(completed))[-TREND_MONTHS:]
    return [
        MonthlyPoint(month=m, created=created.get(m, 0), completed=completed.get(m, 0))
        for m in months
    ]


async def _by_category(session: AsyncSession, caller) -> list[CategoryCount]:
    total_expr = func.count(Request.id)
    done_expr = func.count(case((Request.status == RequestStatus.COMPLETED.value, 1)))
    rows = (
        await session.execute(
            _scope_stmt(
                select(
                    Category.slug,
                    Category.label_uz,
                    total_expr.label("total"),
                    done_expr.label("done"),
                ).join(Category, Category.slug == Request.category_slug),
                caller,
            )
            .group_by(Category.slug, Category.label_uz)
            .order_by(total_expr.desc())
        )
    ).all()
    return [
        CategoryCount(slug=slug, label=label, total=total, completed=done)
        for slug, label, total, done in rows
    ]


async def _ratings(
    session: AsyncSession, caller
) -> tuple[list[RatingBucket], float | None, int]:
    """Score distribution over requests in scope.

    Joined through ``requests`` rather than read straight off ``ratings`` so the same
    scoping rule applies here as everywhere else — an employee must not see the centre's
    whole rating history just because ratings live in their own table.
    """
    rows = dict(
        (
            await session.execute(
                _scope_stmt(
                    select(Rating.score, func.count()).join(
                        Request, Request.id == Rating.request_id
                    ),
                    caller,
                ).group_by(Rating.score)
            )
        ).all()
    )
    buckets = [RatingBucket(score=score, count=rows.get(score, 0)) for score in range(1, 6)]
    total = sum(rows.values())
    average = sum(score * count for score, count in rows.items()) / total if total else None
    return buckets, average, total


async def _resolution(session: AsyncSession, caller) -> ResolutionStats:
    """How long finished work took, in hours."""
    hours = func.extract("epoch", Request.completed_at - Request.created_at) / 3600.0

    finished = _scope_stmt(select(Request.id), caller).where(
        Request.status == RequestStatus.COMPLETED.value,
        Request.completed_at.isnot(None),
    )

    row = (
        await session.execute(
            select(
                func.avg(hours),
                # percentile_cont, not avg alone: one request that sat open over a holiday
                # drags the mean somewhere no real request ever was.
                func.percentile_cont(0.5).within_group(hours),
                func.min(hours),
                func.max(hours),
            )
            .select_from(Request)
            .where(Request.id.in_(finished))
        )
    ).one()

    on_time, late = (
        await session.execute(
            select(
                func.count(case((Request.completed_at <= Request.deadline_at, 1))),
                func.count(case((Request.completed_at > Request.deadline_at, 1))),
            )
            .select_from(Request)
            .where(Request.id.in_(finished), Request.deadline_at.isnot(None))
        )
    ).one()

    def as_float(value) -> float | None:
        return float(value) if value is not None else None

    return ResolutionStats(
        average_hours=as_float(row[0]),
        median_hours=as_float(row[1]),
        fastest_hours=as_float(row[2]),
        slowest_hours=as_float(row[3]),
        on_time=on_time or 0,
        late=late or 0,
    )


async def _staff_load(session: AsyncSession) -> list[StaffLoad]:
    """Open and completed work per RTM staff member.

    Not scoped: this panel is about the team as a whole. Counted through
    ``request_assignees`` so a job two people shared counts for both of them.
    """
    open_expr = func.count(case((Request.status.in_(OPEN_STATUSES), 1)))
    done_expr = func.count(case((Request.status == RequestStatus.COMPLETED.value, 1)))

    rows = (
        await session.execute(
            select(
                Employee.id,
                Employee.full_name,
                open_expr.label("open_count"),
                done_expr.label("done_count"),
            )
            .select_from(RequestAssignee)
            .join(Request, Request.id == RequestAssignee.request_id)
            .join(Employee, Employee.id == RequestAssignee.employee_id)
            .group_by(Employee.id, Employee.full_name)
            .order_by((open_expr + done_expr).desc())
            .limit(TOP_STAFF)
        )
    ).all()

    scores = dict(
        (
            await session.execute(
                select(Rating.rated_employee_id, func.avg(Rating.score)).group_by(
                    Rating.rated_employee_id
                )
            )
        ).all()
    )

    return [
        StaffLoad(
            employee_id=employee_id,
            full_name=full_name,
            open_count=open_count,
            completed_count=done_count,
            average_score=float(scores[employee_id]) if scores.get(employee_id) else None,
        )
        for employee_id, full_name, open_count, done_count in rows
    ]
