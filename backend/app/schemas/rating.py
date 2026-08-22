from pydantic import BaseModel, Field


class RatingCreate(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = None


class RatingResponse(BaseModel):
    id: int
    request_id: int
    rated_employee_id: int
    score: int
    comment: str | None

    class Config:
        from_attributes = True


class StaffRatingSummary(BaseModel):
    employee_id: int
    full_name: str
    completed_count: int
    average_score: float | None
    rating_count: int
