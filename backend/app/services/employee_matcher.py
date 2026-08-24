"""Resolve a HEMIS OAuth user to a local Employee row.

The local employee roster is populated by a *different* HEMIS integration (the bulk sync,
which uses a static bearer token against student.alfraganusuniversity.uz). It is not
confirmed that the OAuth userinfo ``id`` is the same identifier as the sync API's employee
``id``, nor what ``login`` contains. Rather than guess one mapping and fail opaquely, we try
each plausible mapping in turn and record which one worked.

Once a login succeeds, ``hemis_oauth_subject`` is written to the employee, so every later
login for that person short-circuits on the first rung.
"""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Employee
from afu_shared.settings import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MatchResult:
    employee: Employee
    strategy: str


def _text(userinfo: dict[str, Any], key: str) -> str | None:
    value = userinfo.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _one(session: AsyncSession, condition: Any) -> Employee | None:
    return (await session.execute(select(Employee).where(condition))).scalar_one_or_none()


async def _by_id_number(session: AsyncSession, value: str | None) -> Employee | None:
    """Match on employee_id_number, tolerating inconsistent zero-padding."""
    if not value:
        return None
    found = await _one(session, Employee.employee_id_number == value)
    if found is not None:
        return found

    # Normalize BOTH sides: either the incoming value or the stored one may carry leading
    # zeros the other lacks, so stripping only the incoming value misses half the cases.
    stripped = value.lstrip("0")
    if not stripped:
        return None
    return await _one(session, func.ltrim(Employee.employee_id_number, "0") == stripped)


async def match_employee(session: AsyncSession, userinfo: dict[str, Any]) -> MatchResult | None:
    oauth_id = _text(userinfo, "id")
    uuid = _text(userinfo, "uuid")
    login = _text(userinfo, "login")
    university_id = _text(userinfo, "university_id")
    email = _text(userinfo, "email")
    name = _text(userinfo, "name")

    # Ordered most- to least-trustworthy. Each rung is skipped when its source value is absent.
    if oauth_id:
        found = await _one(session, Employee.hemis_oauth_subject == oauth_id)
        if found:
            return MatchResult(found, "oauth_subject")

    if uuid:
        found = await _one(session, Employee.hemis_uuid == uuid)
        if found:
            return MatchResult(found, "hemis_uuid")

    if (numeric_id := _as_int(oauth_id)) is not None:
        found = await _one(session, Employee.hemis_id == numeric_id)
        if found:
            return MatchResult(found, "hemis_id")

    if found := await _by_id_number(session, login):
        return MatchResult(found, "login_as_id_number")

    if found := await _by_id_number(session, university_id):
        return MatchResult(found, "university_id_as_id_number")

    if found := await _by_id_number(session, oauth_id):
        return MatchResult(found, "id_as_id_number")

    if (numeric_login := _as_int(login)) is not None:
        found = await _one(session, Employee.hemis_id == numeric_login)
        if found:
            return MatchResult(found, "login_as_hemis_id")

    if email:
        found = await _one(session, func.lower(Employee.hemis_email) == email.lower())
        if found:
            return MatchResult(found, "hemis_email")

    if name:
        # Names are not identifiers. Only accept when exactly one employee matches —
        # two people sharing a name must never be silently collapsed into one account.
        rows = (
            await session.execute(
                select(Employee).where(func.lower(Employee.full_name) == name.lower()).limit(2)
            )
        ).scalars().all()
        if len(rows) == 1:
            return MatchResult(rows[0], "full_name_exact")
        if len(rows) > 1:
            logger.warning("HEMIS OAuth: full_name %r is ambiguous, refusing to match", name)

    logger.warning(
        "HEMIS OAuth: no employee matched. Probed hemis_oauth_subject, hemis_uuid, hemis_id, "
        "employee_id_number (from login/university_id/id), hemis_email, full_name. userinfo=%s",
        userinfo if settings.oauth_debug_log_userinfo else "<logging disabled>",
    )
    return None
