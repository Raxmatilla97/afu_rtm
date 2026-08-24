from pydantic import BaseModel, EmailStr


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AdminMeResponse(BaseModel):
    id: int
    email: str
    role: str


class EmployeeMeResponse(BaseModel):
    """The signed-in employee, including what they are allowed to do.

    The role flags travel with identity rather than being fetched per page: the interface
    has to decide whether to draw an assignment control before it knows anything else."""

    id: int
    full_name: str
    employee_id_number: str
    department_name: str | None
    is_rtm_staff: bool
    is_supervisor: bool = False
    is_admin: bool = False
    can_manage_assignments: bool = False
    phone_number: str | None
    telegram_username: str | None
