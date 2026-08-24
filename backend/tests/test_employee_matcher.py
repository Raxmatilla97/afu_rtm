"""Tests for the employee matching cascade.

Runs against a real Postgres (the compose one), because the matcher leans on SQL functions
like ltrim/lower that a fake session would not exercise.
"""

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from afu_shared.models import Base, Employee
from app.services.employee_matcher import match_employee

DATABASE_URL = os.environ["DATABASE_URL"]

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


def _employee(**overrides) -> Employee:
    unique = uuid.uuid4().hex[:10]
    defaults = dict(
        employee_id_number=f"T{unique}",
        full_name=f"TEST USER {unique}",
        employee_status_code="11",
        is_active=True,
    )
    return Employee(**{**defaults, **overrides})


async def _add(session: AsyncSession, employee: Employee) -> Employee:
    session.add(employee)
    await session.flush()
    return employee


async def test_matches_on_oauth_subject_first(session):
    emp = await _add(session, _employee(hemis_oauth_subject="sub-9001"))
    result = await match_employee(session, {"id": "sub-9001"})
    assert result is not None
    assert result.employee.id == emp.id
    assert result.strategy == "oauth_subject"


async def test_matches_on_hemis_uuid(session):
    emp = await _add(session, _employee(hemis_uuid="uuid-7788"))
    result = await match_employee(session, {"uuid": "uuid-7788"})
    assert result.employee.id == emp.id
    assert result.strategy == "hemis_uuid"


async def test_matches_on_hemis_id(session):
    emp = await _add(session, _employee(hemis_id=987654))
    result = await match_employee(session, {"id": 987654})
    assert result.employee.id == emp.id
    assert result.strategy == "hemis_id"


def _unique_digits() -> str:
    """A numeric id that cannot collide with real synced employees in the dev database."""
    return str(uuid.uuid4().int)[:12]


async def test_matches_login_against_employee_id_number(session):
    number = _unique_digits()
    emp = await _add(session, _employee(employee_id_number=number))
    result = await match_employee(session, {"id": "nope", "login": number})
    assert result.employee.id == emp.id
    assert result.strategy == "login_as_id_number"


async def test_matches_university_id_against_employee_id_number(session):
    number = _unique_digits()
    emp = await _add(session, _employee(employee_id_number=number))
    result = await match_employee(session, {"id": "nope", "university_id": number})
    assert result.employee.id == emp.id
    assert result.strategy == "university_id_as_id_number"


async def test_matches_when_stored_value_is_zero_padded(session):
    # ID numbers are zero-padded inconsistently between systems: stored with zeros,
    # supplied without.
    number = _unique_digits()
    emp = await _add(session, _employee(employee_id_number=f"00{number}"))
    result = await match_employee(session, {"id": "x", "login": number})
    assert result is not None
    assert result.employee.id == emp.id


async def test_matches_when_supplied_value_is_zero_padded(session):
    # ...and the mirror case: stored without zeros, supplied with them.
    number = _unique_digits()
    emp = await _add(session, _employee(employee_id_number=number))
    result = await match_employee(session, {"id": "x", "login": f"00{number}"})
    assert result is not None
    assert result.employee.id == emp.id


async def test_matches_email_case_insensitively(session):
    emp = await _add(session, _employee(hemis_email="Someone@Afu.Uz"))
    result = await match_employee(session, {"id": "x", "email": "someone@afu.uz"})
    assert result.employee.id == emp.id
    assert result.strategy == "hemis_email"


async def test_matches_unique_full_name(session):
    name = f"UNIQUE PERSON {uuid.uuid4().hex[:8]}"
    emp = await _add(session, _employee(full_name=name))
    result = await match_employee(session, {"id": "x", "name": name.lower()})
    assert result.employee.id == emp.id
    assert result.strategy == "full_name_exact"


async def test_refuses_ambiguous_full_name(session):
    # Two people sharing a name must never be collapsed into one account.
    name = f"AMBIGUOUS {uuid.uuid4().hex[:8]}"
    await _add(session, _employee(full_name=name))
    await _add(session, _employee(full_name=name))
    assert await match_employee(session, {"id": "x", "name": name}) is None


async def test_returns_none_when_nothing_matches(session):
    assert await match_employee(session, {"id": "no-such-id-12345"}) is None


async def test_empty_userinfo_matches_nothing(session):
    await _add(session, _employee())
    assert await match_employee(session, {}) is None
