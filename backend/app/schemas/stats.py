from pydantic import BaseModel


class MonthlyCount(BaseModel):
    month: str
    count: int


class StatsSummary(BaseModel):
    total_requests: int
    new_count: int
    assigned_count: int
    in_progress_count: int
    completed_count: int
    cancelled_count: int
