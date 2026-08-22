from datetime import datetime

from pydantic import BaseModel, EmailStr


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AdminMeResponse(BaseModel):
    id: int
    email: str
    role: str


class TelegramLinkStartRequest(BaseModel):
    employee_id_number: str


class TelegramLinkStartResponse(BaseModel):
    token: str
    deep_link: str
    expires_at: datetime


class TelegramLinkStatusResponse(BaseModel):
    status: str
    session_ready: bool


class EmployeeMeResponse(BaseModel):
    id: int
    full_name: str
    employee_id_number: str
    department_name: str | None
    is_rtm_staff: bool
    phone_number: str | None
    telegram_username: str | None
