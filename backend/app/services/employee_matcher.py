"""Resolve a HEMIS OAuth user to a local Employee row.

The local employee roster is populated by a *different* HEMIS integration (the bulk sync,
which uses a static bearer token against student.alfraganusuniversity.uz), so the two sides
do not share an id space. Every rung here therefore compares values of the *same kind* —
a subject to a subject, an id number to an id number, an address to an address.

**No rung guesses across id spaces, and none matches on a name.** Earlier versions did
both: the OAuth ``id`` was tried against ``employees.hemis_id`` (two unrelated counters
that collide freely) and, as a last resort, ``name`` was matched against ``full_name``.
Either could hand somebody a colleague's account — which is exactly what happened: people
signed in and found themselves under another person's name and department. Refusing to
match is now the correct outcome for an unrecognised account: the quick login (id number
plus a local password) is the way in for anyone HEMIS cannot place.

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

    # Ordered most- to least-trustworthy. Each rung is skipped when its source value is absent.
    if oauth_id:
        found = await _one(session, Employee.hemis_oauth_subject == oauth_id)
        if found:
            return MatchResult(found, "oauth_subject")

    if uuid:
        found = await _one(session, Employee.hemis_uuid == uuid)
        if found:
            return MatchResult(found, "hemis_uuid")

    if found := await _by_id_number(session, login):
        return MatchResult(found, "login_as_id_number")

    if found := await _by_id_number(session, university_id):
        return MatchResult(found, "university_id_as_id_number")

    if email:
        found = await _one(session, func.lower(Employee.hemis_email) == email.lower())
        if found:
            return MatchResult(found, "hemis_email")

    logger.warning(
        "HEMIS OAuth: no employee matched. Probed hemis_oauth_subject, hemis_uuid, "
        "employee_id_number (from login and university_id) and hemis_email. userinfo=%s",
        userinfo if settings.oauth_debug_log_userinfo else "<logging disabled>",
    )
    return None
