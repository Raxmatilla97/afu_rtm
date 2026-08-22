from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Employee, User
from app.deps import get_current_admin, get_db
from app.schemas.employee import EmployeeResponse

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=list[EmployeeResponse])
async def list_employees(
    q: str | None = None,
    department_id: int | None = None,
    is_rtm_staff: bool | None = None,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
) -> list[EmployeeResponse]:
    stmt = select(Employee)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Employee.full_name.ilike(like), Employee.employee_id_number.ilike(like)))
    if department_id is not None:
        stmt = stmt.where(Employee.department_id == department_id)
    if is_rtm_staff is not None:
        stmt = stmt.where(Employee.is_rtm_staff == is_rtm_staff)
    stmt = stmt.order_by(Employee.full_name).limit(500)

    result = await session.execute(stmt)
    return [EmployeeResponse.from_employee(e) for e in result.scalars()]


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int, admin: User = Depends(get_current_admin), session: AsyncSession = Depends(get_db)
) -> EmployeeResponse:
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return EmployeeResponse.from_employee(employee)


@router.post("/{employee_id}/promote-to-staff", response_model=EmployeeResponse)
async def promote_to_staff(
    employee_id: int, admin: User = Depends(get_current_admin), session: AsyncSession = Depends(get_db)
) -> EmployeeResponse:
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    employee.is_rtm_staff = True
    await session.flush()
    return EmployeeResponse.from_employee(employee)


@router.post("/{employee_id}/demote", response_model=EmployeeResponse)
async def demote_from_staff(
    employee_id: int, admin: User = Depends(get_current_admin), session: AsyncSession = Depends(get_db)
) -> EmployeeResponse:
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    employee.is_rtm_staff = False
    await session.flush()
    return EmployeeResponse.from_employee(employee)


@router.post("/{employee_id}/revoke", response_model=EmployeeResponse)
async def revoke_access(
    employee_id: int, admin: User = Depends(get_current_admin), session: AsyncSession = Depends(get_db)
) -> EmployeeResponse:
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    employee.access_revoked = True
    employee.access_revoked_at = datetime.now(timezone.utc)
    await session.flush()
    return EmployeeResponse.from_employee(employee)
