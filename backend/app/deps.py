from collections.abc import AsyncIterator

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.db import async_session_factory
from afu_shared.models import Employee, User
from afu_shared.settings import settings
from app.security import decode_access_token


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_admin(
    session: AsyncSession = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> User:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if not session_token:
        raise unauthorized
    payload = decode_access_token(session_token)
    if not payload or payload.get("scope") != "admin":
        raise unauthorized
    user = await session.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise unauthorized
    return user


async def get_current_employee(
    session: AsyncSession = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> Employee:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if not session_token:
        raise unauthorized
    payload = decode_access_token(session_token)
    if not payload or payload.get("scope") != "employee":
        raise unauthorized
    employee = await session.get(Employee, int(payload["sub"]))
    if not employee or not employee.is_eligible:
        raise unauthorized
    return employee


async def get_current_rtm_staff(
    employee: Employee = Depends(get_current_employee),
) -> Employee:
    if not employee.is_rtm_staff:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="RTM staff only")
    return employee


async def get_current_caller(
    session: AsyncSession = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> User | Employee:
    """Either an admin (User) or a verified employee, whichever scope the session cookie carries."""
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if not session_token:
        raise unauthorized
    payload = decode_access_token(session_token)
    if not payload:
        raise unauthorized

    if payload.get("scope") == "admin":
        user = await session.get(User, int(payload["sub"]))
        if not user or not user.is_active:
            raise unauthorized
        return user

    if payload.get("scope") == "employee":
        employee = await session.get(Employee, int(payload["sub"]))
        if not employee or not employee.is_eligible:
            raise unauthorized
        return employee

    raise unauthorized
