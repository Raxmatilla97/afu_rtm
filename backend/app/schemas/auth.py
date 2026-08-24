from pydantic import BaseModel, EmailStr


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AdminMeResponse(BaseModel):
    id: int
    email: str
    role: str


class EmployeeMeResponse(BaseModel):
    id: int
    full_name: str
    employee_id_number: str
    department_name: str | None
    is_rtm_staff: bool
    phone_number: str | None
    telegram_username: str | None
