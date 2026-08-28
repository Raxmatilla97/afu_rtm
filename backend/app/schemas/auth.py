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

    @classmethod
    def from_employee(cls, employee) -> "EmployeeMeResponse":
        return cls(
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


class QuickLookupRequest(BaseModel):
    employee_id_number: str


class QuickLookupResponse(BaseModel):
    """What the login form should ask for next, and who it is about to sign in.

    The name is returned before the password on purpose. People have been landing in the
    system under a colleague's identity, and the only way to stop that being a surprise is
    to show whose account is about to be opened while there is still time to say "that is
    not me".
    """

    status: str
    full_name: str | None = None
    department_name: str | None = None
    #: Present only when a reset can actually be offered.
    masked_email: str | None = None
    locked_minutes: int = 0


class QuickLoginRequest(BaseModel):
    employee_id_number: str
    password: str


class QuickSetupRequest(BaseModel):
    """First claim of an account: password and the address a reset would go to."""

    employee_id_number: str
    password: str
    recovery_email: EmailStr


class QuickForgotRequest(BaseModel):
    employee_id_number: str


class QuickForgotResponse(BaseModel):
    sent: bool
    masked_email: str | None = None
    message: str


class QuickResetRequest(BaseModel):
    token: str
    password: str
