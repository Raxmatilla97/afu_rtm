import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import TelegramLinkPurpose, TelegramLinkStatus
from afu_shared.models import Employee, TelegramLinkToken, User
from afu_shared.settings import settings
from app.deps import get_current_admin, get_current_employee, get_db
from app.schemas.auth import (
    AdminLoginRequest,
    AdminMeResponse,
    EmployeeMeResponse,
    TelegramLinkStartRequest,
    TelegramLinkStartResponse,
    TelegramLinkStatusResponse,
)
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

TELEGRAM_LINK_TOKEN_TTL_MINUTES = 10


def _set_session_cookie(response: Response, *, subject: str, scope: str) -> None:
    token = create_access_token(subject=subject, scope=scope, expires_days=settings.session_ttl_days)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_ttl_days * 24 * 3600,
    )


@router.post("/login", response_model=AdminMeResponse)
async def admin_login(
    payload: AdminLoginRequest, response: Response, session: AsyncSession = Depends(get_db)
) -> User:
    user = (
        await session.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user.last_login_at = datetime.now(timezone.utc)
    _set_session_cookie(response, subject=str(user.id), scope="admin")
    return user


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(settings.session_cookie_name)
    return {"ok": True}


@router.get("/me", response_model=AdminMeResponse)
async def admin_me(admin: User = Depends(get_current_admin)) -> User:
    return admin


@router.get("/employee/me", response_model=EmployeeMeResponse)
async def employee_me(employee: Employee = Depends(get_current_employee)) -> EmployeeMeResponse:
    return EmployeeMeResponse(
        id=employee.id,
        full_name=employee.full_name,
        employee_id_number=employee.employee_id_number,
        department_name=employee.department.name if employee.department else None,
        is_rtm_staff=employee.is_rtm_staff,
        phone_number=employee.phone_number,
        telegram_username=employee.telegram_username,
    )


@router.post("/telegram-link/start", response_model=TelegramLinkStartResponse)
async def telegram_link_start(
    payload: TelegramLinkStartRequest, session: AsyncSession = Depends(get_db)
) -> TelegramLinkStartResponse:
    employee = (
        await session.execute(
            select(Employee).where(Employee.employee_id_number == payload.employee_id_number)
        )
    ).scalar_one_or_none()
    if not employee or not employee.is_eligible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Xodim topilmadi yoki tizimdan foydalanish huquqi yo'q",
        )

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=TELEGRAM_LINK_TOKEN_TTL_MINUTES)
    session.add(
        TelegramLinkToken(
            token=token,
            employee_id=employee.id,
            purpose=TelegramLinkPurpose.INITIAL_VERIFICATION.value,
            status=TelegramLinkStatus.PENDING.value,
            expires_at=expires_at,
        )
    )
    await session.flush()

    bot_username = settings.telegram_bot_username
    deep_link = f"https://t.me/{bot_username}?start={token}" if bot_username else ""
    return TelegramLinkStartResponse(token=token, deep_link=deep_link, expires_at=expires_at)


@router.get("/telegram-link/{token}", response_model=TelegramLinkStatusResponse)
async def telegram_link_status(
    token: str, response: Response, session: AsyncSession = Depends(get_db)
) -> TelegramLinkStatusResponse:
    link = await session.get(TelegramLinkToken, token)
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    if link.status == TelegramLinkStatus.PENDING.value and link.expires_at < datetime.now(timezone.utc):
        link.status = TelegramLinkStatus.EXPIRED.value

    session_ready = False
    if link.status == TelegramLinkStatus.COMPLETED.value:
        _set_session_cookie(response, subject=str(link.employee_id), scope="employee")
        session_ready = True

    return TelegramLinkStatusResponse(status=link.status, session_ready=session_ready)
