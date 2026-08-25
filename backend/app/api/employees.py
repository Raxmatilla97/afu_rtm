from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Employee, User
from app.deps import get_admin_actor, get_current_caller, get_db
from app.schemas.employee import EmployeeResponse, EmployeeRolesUpdate

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=list[EmployeeResponse])
async def list_employees(
    q: str | None = None,
    department_id: int | None = None,
    is_rtm_staff: bool | None = None,
    actor: User | Employee = Depends(get_admin_actor),
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


@router.get("/rtm-staff", response_model=list[EmployeeResponse])
async def list_rtm_staff(
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> list[EmployeeResponse]:
    """Who a request can be handed to.

    Declared above ``/{employee_id}`` because FastAPI matches in order, and a literal path
    that comes second is a path that never matches.

    Open to Boshliq as well as Admin, unlike the full directory below. Assigning work is
    exactly what the Boshliq role is for, and both the assign form and the staff filter on
    the request list were dead for them while the only list of staff sat behind an
    admin-only endpoint — the form rendered with no names in it and looked broken.
    """
    if isinstance(caller, Employee) and not caller.can_manage_assignments:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Faqat Boshliq yoki Admin"
        )

    stmt = select(Employee).where(Employee.is_rtm_staff.is_(True)).order_by(Employee.full_name)
    return [EmployeeResponse.from_employee(e) for e in (await session.execute(stmt)).scalars()]


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int, actor: User | Employee = Depends(get_admin_actor), session: AsyncSession = Depends(get_db)
) -> EmployeeResponse:
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return EmployeeResponse.from_employee(employee)


@router.post("/{employee_id}/promote-to-staff", response_model=EmployeeResponse)
async def promote_to_staff(
    employee_id: int, actor: User | Employee = Depends(get_admin_actor), session: AsyncSession = Depends(get_db)
) -> EmployeeResponse:
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    employee.is_rtm_staff = True
    await session.flush()
    return EmployeeResponse.from_employee(employee)


@router.post("/{employee_id}/demote", response_model=EmployeeResponse)
async def demote_from_staff(
    employee_id: int, actor: User | Employee = Depends(get_admin_actor), session: AsyncSession = Depends(get_db)
) -> EmployeeResponse:
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    employee.is_rtm_staff = False
    await session.flush()
    return EmployeeResponse.from_employee(employee)


@router.post("/{employee_id}/roles", response_model=EmployeeResponse)
async def update_roles(
    employee_id: int,
    payload: EmployeeRolesUpdate,
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """Set any subset of an employee's flags.

    One endpoint for all of them, taking only the fields that were sent, because the admin
    table toggles them individually: a per-flag endpoint would be four near-identical
    handlers, and a whole-object PUT would let one toggle silently reset the rest.
    """
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    if payload.is_rtm_staff is not None:
        employee.is_rtm_staff = payload.is_rtm_staff
    if payload.is_supervisor is not None:
        employee.is_supervisor = payload.is_supervisor
    if payload.is_admin is not None:
        employee.is_admin = payload.is_admin
    if payload.is_blocked is not None and payload.is_blocked != employee.is_blocked:
        employee.is_blocked = payload.is_blocked
        employee.blocked_at = datetime.now(timezone.utc) if payload.is_blocked else None

    await session.flush()
    return EmployeeResponse.from_employee(employee)


@router.post("/{employee_id}/revoke", response_model=EmployeeResponse)
async def revoke_access(
    employee_id: int, actor: User | Employee = Depends(get_admin_actor), session: AsyncSession = Depends(get_db)
) -> EmployeeResponse:
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    employee.access_revoked = True
    employee.access_revoked_at = datetime.now(timezone.utc)
    await session.flush()
    return EmployeeResponse.from_employee(employee)
