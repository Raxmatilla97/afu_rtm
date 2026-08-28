from datetime import datetime

from pydantic import BaseModel, field_validator


class EmployeeProfileUpdate(BaseModel):
    """What an administrator may correct by hand on an employee's record.

    Every field is optional and only the ones actually sent are written, so the dialog can
    save one corrected phone number without touching anything else.

    Four of these — the name, the department, the year and the HEMIS contact details — are
    also written by the HEMIS sync, which will overwrite an edit on its next run. They are
    editable anyway because HEMIS is frequently wrong or empty and somebody has to be able
    to fix a name today; the interface says plainly which fields are borrowed.

    Deliberately absent: ``employee_id_number`` (the sync's join key — changing it splits
    the person into two rows on the next run), ``is_active`` and ``employee_status_code``
    (both decide ``is_eligible``, so a slip there locks somebody out of the bot and the
    site at once, with nothing on screen to explain why). Blocking has its own toggle.
    """

    full_name: str | None = None
    department_id: int | None = None
    phone_number: str | None = None
    telegram_username: str | None = None
    recovery_email: str | None = None
    hemis_email: str | None = None
    hemis_phone: str | None = None
    year_of_enter: int | None = None

    @field_validator(
        "full_name",
        "phone_number",
        "telegram_username",
        "recovery_email",
        "hemis_email",
        "hemis_phone",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value):
        """An emptied input means "clear this", not "store an empty string".

        Without it a cleared field reads as present-but-blank everywhere downstream, and
        "—" in the panel would start meaning two different things.
        """
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("telegram_username", mode="after")
    @classmethod
    def _strip_at(cls, value: str | None) -> str | None:
        # Stored bare, because every place that shows it adds the @ back.
        if not value:
            return value
        return value.lstrip("@") or None


class EmployeeRolesUpdate(BaseModel):
    """Partial update of an employee's flags — only what is sent is changed."""

    is_rtm_staff: bool | None = None
    is_supervisor: bool | None = None
    is_admin: bool | None = None
    is_blocked: bool | None = None


class EmployeeResponse(BaseModel):
    """One employee, as the admin panel shows them.

    Carries the whole profile rather than the few columns the table prints, because the
    detail dialog is opened from a row that is already in memory — fetching the same person
    again just to read their HEMIS login would be a round trip for data the list query
    already had in hand.
    """

    id: int
    hemis_id: int | None = None
    employee_id_number: str
    full_name: str
    department_id: int | None
    department_name: str | None = None
    employee_status_code: str | None
    is_active: bool
    year_of_enter: int | None
    is_rtm_staff: bool
    is_supervisor: bool = False
    is_admin: bool = False
    is_blocked: bool = False
    blocked_at: datetime | None = None
    access_revoked: bool
    access_revoked_at: datetime | None = None
    telegram_user_id: int | None
    telegram_username: str | None
    phone_number: str | None
    verified_at: datetime | None
    image_local_path: str | None
    #: What HEMIS said the photo is, whether or not it downloaded. Null here with no local
    #: copy is the difference between "HEMIS has no photo of this person" and "the download
    #: failed" — the first question anybody asks about a page full of initials.
    image_source_url: str | None = None
    #: When an administrator uploaded this portrait by hand. Set means the HEMIS sync will
    #: leave it alone, which is the one thing anybody looking at this needs to know.
    image_manual_at: datetime | None = None

    #: How many requests this person has filed. Zero for endpoints that do not count.
    request_count: int = 0

    # --- Quick login. Shown in the admin panel because "who claimed this account, and
    # --- when" is the only audit an id-number login can offer.
    has_quick_password: bool = False
    password_set_at: datetime | None = None
    recovery_email: str | None = None

    # --- HEMIS identity, filled by the OAuth login rather than the bulk sync ---
    hemis_login: str | None = None
    hemis_email: str | None = None
    hemis_phone: str | None = None
    hemis_university_id: str | None = None
    oauth_verified_at: datetime | None = None
    last_synced_at: datetime | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True

    @classmethod
    def from_employee(cls, employee, *, request_count: int = 0) -> "EmployeeResponse":
        return cls(
            id=employee.id,
            request_count=request_count,
            hemis_id=employee.hemis_id,
            employee_id_number=employee.employee_id_number,
            full_name=employee.full_name,
            department_id=employee.department_id,
            department_name=employee.department.name if employee.department else None,
            employee_status_code=employee.employee_status_code,
            is_active=employee.is_active,
            year_of_enter=employee.year_of_enter,
            is_rtm_staff=employee.is_rtm_staff,
            is_supervisor=employee.is_supervisor,
            is_admin=employee.is_admin,
            is_blocked=employee.is_blocked,
            blocked_at=employee.blocked_at,
            access_revoked=employee.access_revoked,
            access_revoked_at=employee.access_revoked_at,
            telegram_user_id=employee.telegram_user_id,
            telegram_username=employee.telegram_username,
            phone_number=employee.phone_number,
            verified_at=employee.verified_at,
            image_local_path=employee.image_local_path,
            image_source_url=employee.image_source_url,
            image_manual_at=employee.image_manual_at,
            has_quick_password=bool(employee.quick_password_hash),
            password_set_at=employee.password_set_at,
            recovery_email=employee.recovery_email,
            hemis_login=employee.hemis_login,
            hemis_email=employee.hemis_email,
            hemis_phone=employee.hemis_phone,
            hemis_university_id=employee.hemis_university_id,
            oauth_verified_at=employee.oauth_verified_at,
            last_synced_at=employee.last_synced_at,
            created_at=employee.created_at,
        )
