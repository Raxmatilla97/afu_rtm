from pydantic import BaseModel


class DepartmentResponse(BaseModel):
    id: int
    hemis_id: int
    name: str
    code: str | None
    parent_department_id: int | None
    is_active: bool

    class Config:
        from_attributes = True
