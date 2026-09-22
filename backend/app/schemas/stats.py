from pydantic import BaseModel


class MonthlyCount(BaseModel):
    month: str
    count: int


class StatsSummary(BaseModel):
    total_requests: int
    new_count: int
    assigned_count: int
    in_progress_count: int
    waiting_count: int = 0
    completed_count: int
    cancelled_count: int
    returned_count: int = 0


class MonthlyPoint(BaseModel):
    """Both series for one month.

    Created and completed are the same unit, so they belong on one axis in one chart —
    which is the only way to see the thing that matters: whether the queue is growing.
    """

    month: str
    created: int
    completed: int


class CategoryCount(BaseModel):
    slug: str
    label: str
    total: int
    completed: int


class RatingBucket(BaseModel):
    score: int
    count: int


class ResolutionStats(BaseModel):
    """How long finished work took, in hours."""

    average_hours: float | None = None
    median_hours: float | None = None
    fastest_hours: float | None = None
    slowest_hours: float | None = None
    #: Of the requests that had a deadline, how many closed before it.
    on_time: int = 0
    late: int = 0


class StaffLoad(BaseModel):
    employee_id: int
    full_name: str
    open_count: int
    completed_count: int
    average_score: float | None = None


class StatsOverview(BaseModel):
    """Everything the statistics page draws, in one round trip.

    One endpoint rather than seven: the page shows a single coherent picture, and seven
    independent fetches would let its panels disagree with each other while they arrive.
    """

    #: Which slice of the queue these numbers cover: ``all`` for a panel admin, Boshliq or
    #: Admin, ``assigned`` for an RTM staffer's own workload, ``own`` for everybody else's
    #: reported requests. Sent so the page can say so out loud — a staffer reading "3 ta
    #: murojaat" over a centre handling three hundred has to be told which three.
    scope: str = "all"
    summary: StatsSummary
    monthly: list[MonthlyPoint] = []
    by_category: list[CategoryCount] = []
    ratings: list[RatingBucket] = []
    average_rating: float | None = None
    rating_count: int = 0
    resolution: ResolutionStats
    staff_load: list[StaffLoad] = []
    open_overdue: int = 0
    unassigned: int = 0
