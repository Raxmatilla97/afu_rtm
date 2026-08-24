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


class AttachmentKind(StrEnum):
    """What an attachment is, in Telegram's vocabulary.

    Stored rather than derived from the MIME type because the distinctions that matter to
    us are Telegram's, not the file system's: a ``voice`` and an ``audio`` are both OGG/MP3,
    and a ``video_note`` (the round video) is an ordinary MP4 — but each has to be re-sent
    through a different Bot API method to arrive looking the way the sender meant it.
    """

    PHOTO = "photo"
    VIDEO = "video"
    VOICE = "voice"
    VIDEO_NOTE = "video_note"
    AUDIO = "audio"
    DOCUMENT = "document"


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


class OAuthFlow(StrEnum):
    WEB = "web"
    BOT = "bot"


class OAuthAttemptStatus(StrEnum):
    PENDING = "pending"
    MATCHED = "matched"
    #: HEMIS authenticated the user, but no local employee row could be resolved.
    UNMATCHED = "unmatched"
    #: Matched an employee who fails Employee.is_eligible.
    INELIGIBLE = "ineligible"
    #: userinfo["type"] explicitly identified a non-employee (e.g. a student).
    WRONG_TYPE = "wrong_type"
    TOKEN_ERROR = "token_error"
    USERINFO_ERROR = "userinfo_error"
    STATE_EXPIRED = "state_expired"
    #: The user declined consent at HEMIS.
    DENIED = "denied"


HEMIS_ACTIVE_EMPLOYEE_STATUS_CODE = "11"
