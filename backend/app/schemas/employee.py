from datetime import datetime

from pydantic import BaseModel


class EmployeeRolesUpdate(BaseModel):
    """Partial update of an employee's flags — only what is sent is changed."""

    is_rtm_staff: bool | None = None
    is_supervisor: bool | None = None
    is_admin: bool | None = None
    is_blocked: bool | None = None


class EmployeeResponse(BaseModel):
    id: int
    employee_id_number: str
    full_name: str
    department_id: int | None
    department_name: str | None = None
    employee_status_code: str | None
    is_active: bool
    year_of_enter: int | None
    is_rtm_staff: bool
    is_supervisor: bool = False
    is_admin: bool = False
    is_blocked: bool = False
    access_revoked: bool
    telegram_user_id: int | None
    telegram_username: str | None
    phone_number: str | None
    verified_at: datetime | None
    image_local_path: str | None

    class Config:
        from_attributes = True

    @classmethod
    def from_employee(cls, employee) -> "EmployeeResponse":
        return cls(
            id=employee.id,
            employee_id_number=employee.employee_id_number,
            full_name=employee.full_name,
            department_id=employee.department_id,
            department_name=employee.department.name if employee.department else None,
            employee_status_code=employee.employee_status_code,
            is_active=employee.is_active,
            year_of_enter=employee.year_of_enter,
            is_rtm_staff=employee.is_rtm_staff,
            is_supervisor=employee.is_supervisor,
            is_admin=employee.is_admin,
            is_blocked=employee.is_blocked,
            access_revoked=employee.access_revoked,
            telegram_user_id=employee.telegram_user_id,
            telegram_username=employee.telegram_username,
            phone_number=employee.phone_number,
            verified_at=employee.verified_at,
            image_local_path=employee.image_local_path,
        )
