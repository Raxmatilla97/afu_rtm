from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Employee, User
from app.deps import get_current_admin, get_current_employee, get_db
from app.schemas.auth import AdminLoginRequest, AdminMeResponse, EmployeeMeResponse
from app.security import verify_password
from app.session import clear_session_cookie, set_session_cookie

router = APIRouter(prefix="/auth", tags=["auth"])


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
    set_session_cookie(response, subject=str(user.id), scope="admin")
    return user


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    clear_session_cookie(response)
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
        is_supervisor=employee.is_supervisor,
        is_admin=employee.is_admin,
        can_manage_assignments=employee.can_manage_assignments,
        phone_number=employee.phone_number,
        telegram_username=employee.telegram_username,
    )
