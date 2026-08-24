from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Department, Employee, User
from app.deps import get_admin_actor, get_db
from app.schemas.department import DepartmentResponse

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("", response_model=list[DepartmentResponse])
async def list_departments(
    actor: User | Employee = Depends(get_admin_actor), session: AsyncSession = Depends(get_db)
) -> list[Department]:
    result = await session.execute(select(Department).order_by(Department.name))
    return list(result.scalars())


@router.get("/{department_id}", response_model=DepartmentResponse)
async def get_department(
    department_id: int, actor: User | Employee = Depends(get_admin_actor), session: AsyncSession = Depends(get_db)
) -> Department:
    department = await session.get(Department, department_id)
    if not department:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    return department
