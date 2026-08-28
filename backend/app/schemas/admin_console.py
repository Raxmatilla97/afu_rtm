from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class SiteConfig(BaseModel):
    """What the site says about itself. Editable from the panel, no deploy involved."""

    title: str = Field(max_length=120)
    description: str = Field(default="", max_length=400)
    keywords: str = Field(default="", max_length=300)
    organization: str = Field(default="", max_length=160)
    contact_email: str = Field(default="", max_length=160)
    contact_phone: str = Field(default="", max_length=60)


class SiteConfigPublic(BaseModel):
    """The subset a signed-out browser is allowed to read."""

    title: str
    description: str
    organization: str


class SmtpTestResult(BaseModel):
    """What happened the last time somebody pressed "send a test letter"."""

    at: str
    to: str
    ok: bool
    message: str | None = None


class SmtpConfigPublic(BaseModel):
    host: str = ""
    port: int = 587
    user: str = ""
    from_address: str = ""
    starttls: bool = True
    #: Never the password itself — only whether one is stored.
    has_password: bool = False
    #: So the answer to a test send appears on the page that asked, not in container logs.
    last_test: SmtpTestResult | None = None


class SmtpConfigUpdate(BaseModel):
    host: str = Field(default="", max_length=200)
    port: int = Field(default=587, ge=1, le=65535)
    user: str = Field(default="", max_length=200)
    #: Empty means "keep the stored password". The form never receives the current one, so
    #: treating empty as "erase" would wipe it every time a host name was corrected.
    password: str = Field(default="", max_length=200)
    from_address: str = Field(default="", max_length=200)
    starttls: bool = True

    @field_validator("host", "user", "from_address", mode="before")
    @classmethod
    def _collapse_whitespace(cls, value: object) -> object:
        """A line break pasted into any of these breaks the SMTP conversation itself.

        Mail headers are line-delimited, so a newline in a From value is both a
        malformed address and the classic header-injection vector. Collapsing every run of
        whitespace to one space fixes the paste and closes the hole in the same step.
        """
        if isinstance(value, str):
            return " ".join(value.split())
        return value


class SmtpTestRequest(BaseModel):
    to_address: EmailStr


class ActivityEventResponse(BaseModel):
    id: int
    created_at: datetime
    source: str
    action: str
    action_label: str
    actor_name: str
    employee_id: int | None = None
    target: str | None = None
    detail: str | None = None


class ActivityDay(BaseModel):
    """One day's usage. Users are distinct people; events are individual actions."""

    day: str
    bot_users: int = 0
    bot_events: int = 0
    web_users: int = 0
    web_events: int = 0


class ActorActivity(BaseModel):
    employee_id: int | None
    actor_name: str
    last_action: str
    last_action_label: str
    last_target: str | None = None
    last_source: str
    last_seen_at: datetime
    events: int = 0
