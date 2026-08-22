from enum import StrEnum


class RequestStatus(StrEnum):
    NEW = "new"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RequestSource(StrEnum):
    BOT = "bot"
    WEB = "web"


class MessageVisibility(StrEnum):
    INTERNAL = "internal"
    TO_REQUESTER = "to_requester"


class TelegramLinkPurpose(StrEnum):
    INITIAL_VERIFICATION = "initial_verification"
    WEB_LOGIN = "web_login"


class TelegramLinkStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"


class HemisSyncStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class UserRole(StrEnum):
    ADMIN = "admin"


HEMIS_ACTIVE_EMPLOYEE_STATUS_CODE = "11"
