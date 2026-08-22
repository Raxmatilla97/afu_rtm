from datetime import datetime

from pydantic import BaseModel


class HemisSyncRunResponse(BaseModel):
    id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    departments_created: int
    departments_updated: int
    employees_created: int
    employees_updated: int
    employees_revoked: int
    error_message: str | None

    class Config:
        from_attributes = True
