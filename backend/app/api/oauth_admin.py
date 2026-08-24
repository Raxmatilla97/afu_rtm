"""Admin view over OAuth login attempts.

This is the operational counterpart to the defensive matching in
``app/services/employee_matcher.py``: when a real login fails to resolve an employee, the
full HEMIS payload is here, which is what makes the correct mapping discoverable.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import OAuthAttemptStatus
from afu_shared.models import OAuthLoginAttempt, User
from app.deps import get_current_admin, get_db

router = APIRouter(prefix="/oauth-attempts", tags=["oauth-attempts"])


class OAuthAttemptResponse(BaseModel):
    state: str
    flow: str
    status: str
    match_strategy: str | None
    matched_employee_id: int | None
    telegram_user_id: int | None
    userinfo_json: dict[str, Any] | None
    error_detail: str | None
    created_at: datetime
    completed_at: datetime | None


@router.get("", response_model=list[OAuthAttemptResponse])
async def list_oauth_attempts(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[OAuthLoginAttempt]:
    # Problems first — a successful login needs no attention, an unmatched one does.
    problems_first = case((OAuthLoginAttempt.status == OAuthAttemptStatus.MATCHED.value, 1), else_=0)
    rows = (
        await session.execute(
            select(OAuthLoginAttempt)
            .order_by(problems_first, OAuthLoginAttempt.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return list(rows)
