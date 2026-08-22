from datetime import datetime

from pydantic import BaseModel

from app.schemas.employee import EmployeeResponse


class RequestCreate(BaseModel):
    category_slug: str
    description: str


class RequestAssign(BaseModel):
    assigned_to_employee_id: int
    deadline_at: datetime | None = None


class RequestStatusUpdate(BaseModel):
    status: str
    note: str | None = None


class RequestComplete(BaseModel):
    completion_note: str


class RequestMessageCreate(BaseModel):
    body: str
    visibility: str = "to_requester"


class RequestMessageResponse(BaseModel):
    id: int
    request_id: int
    author_employee_id: int | None
    author_user_id: int | None
    visibility: str
    body: str
    created_at: datetime

    class Config:
        from_attributes = True


class RequestAttachmentResponse(BaseModel):
    id: int
    request_id: int
    file_path: str
    original_filename: str | None
    content_type: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class RequestResponse(BaseModel):
    id: int
    display_number: str
    requester_employee_id: int
    requester_name: str | None = None
    category_slug: str
    category_label: str | None = None
    description: str
    status: str
    source: str
    assigned_to_employee_id: int | None
    assigned_to_name: str | None = None
    deadline_at: datetime | None
    completed_at: datetime | None
    completion_note: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_request(cls, r) -> "RequestResponse":
        return cls(
            id=r.id,
            display_number=r.display_number,
            requester_employee_id=r.requester_employee_id,
            requester_name=r.requester.full_name if r.requester else None,
            category_slug=r.category_slug,
            category_label=r.category.label_uz if r.category else None,
            description=r.description,
            status=r.status,
            source=r.source,
            assigned_to_employee_id=r.assigned_to_employee_id,
            assigned_to_name=r.assigned_to.full_name if r.assigned_to else None,
            deadline_at=r.deadline_at,
            completed_at=r.completed_at,
            completion_note=r.completion_note,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
