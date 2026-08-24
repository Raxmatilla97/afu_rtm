from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import HemisSyncStatus
from afu_shared.models import Employee, HemisSyncRun, User
from app.arq_pool import get_arq_pool
from app.deps import get_admin_actor, get_db
from app.schemas.hemis_sync import HemisSyncRunResponse

router = APIRouter(prefix="/hemis-sync", tags=["hemis-sync"])


@router.post("/run", response_model=HemisSyncRunResponse)
async def trigger_sync(
    actor: User | Employee = Depends(get_admin_actor), session: AsyncSession = Depends(get_db)
) -> HemisSyncRun:
    run = HemisSyncRun(
        status=HemisSyncStatus.RUNNING.value,
        # Whichever identity started it — the panel account or an employee flagged Admin.
        # One column is filled, never both.
        triggered_by_user_id=actor.id if isinstance(actor, User) else None,
        triggered_by_employee_id=actor.id if isinstance(actor, Employee) else None,
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    await session.flush()
    await session.refresh(run)
    run_id = run.id

    pool = await get_arq_pool()
    await pool.enqueue_job("hemis_sync_task", run_id)

    return run


@router.get("/last", response_model=HemisSyncRunResponse | None)
async def last_sync(
    actor: User | Employee = Depends(get_admin_actor), session: AsyncSession = Depends(get_db)
) -> HemisSyncRun | None:
    result = await session.execute(select(HemisSyncRun).order_by(HemisSyncRun.started_at.desc()).limit(1))
    return result.scalar_one_or_none()


@router.get("/history", response_model=list[HemisSyncRunResponse])
async def sync_history(
    actor: User | Employee = Depends(get_admin_actor), session: AsyncSession = Depends(get_db)
) -> list[HemisSyncRun]:
    result = await session.execute(
        select(HemisSyncRun).order_by(HemisSyncRun.started_at.desc()).limit(50)
    )
    return list(result.scalars())
