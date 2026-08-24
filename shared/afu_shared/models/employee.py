from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from afu_shared.models.department import Department


class Employee(TimestampMixin, Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    hemis_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True, index=True)
    employee_id_number: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False)

    department_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("departments.id"), nullable=True
    )
    department: Mapped["Department | None"] = relationship("Department", lazy="selectin")

    employee_status_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    year_of_enter: Mapped[int | None] = mapped_column(Integer, nullable=True)

    image_source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    image_local_path: Mapped[str | None] = mapped_column(String, nullable=True)

    is_rtm_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: Head of RTM. May hand a request to somebody else — from the group card or the web —
    #: and may take a colleague off one.
    is_supervisor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Employee-level admin. Everything a supervisor can do; distinct from the ``User``
    #: account that signs into the admin panel, which is an email/password login and has
    #: nothing to do with anyone's HEMIS identity.
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: Barred by hand from the admin panel. Deliberately NOT ``access_revoked``: that one
    #: is owned by the HEMIS sync, which clears it again for anybody HEMIS still considers
    #: active — so a manual ban stored there would quietly undo itself overnight.
    is_blocked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    access_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    access_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String, nullable=True)
    # Telegram-verified phone (from the contact share). Distinct from hemis_phone, which HEMIS reports
    # and which may be stale.
    phone_number: Mapped[str | None] = mapped_column(String, nullable=True)
    # Set once the contact share completes — the "fully onboarded" flag.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- HEMIS OAuth2 identity (populated on login; the bulk sync must not overwrite these) ---
    # Stringified userinfo["id"] — the stable key that lets later logins skip the matching cascade.
    hemis_oauth_subject: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    hemis_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    hemis_login: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    hemis_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hemis_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hemis_university_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    oauth_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Employee id={self.id} employee_id_number={self.employee_id_number!r} full_name={self.full_name!r}>"

    @property
    def is_eligible(self) -> bool:
        from afu_shared.enums import HEMIS_ACTIVE_EMPLOYEE_STATUS_CODE

        return (
            self.is_active
            and not self.is_blocked
            and not self.access_revoked
            and self.employee_status_code == HEMIS_ACTIVE_EMPLOYEE_STATUS_CODE
        )

    @property
    def can_manage_assignments(self) -> bool:
        """May decide who works on a request, and take somebody off one.

        Blocked or departed people keep the flag in the database but lose the power with
        it — one check, so a ban cannot be half-applied.
        """
        return self.is_eligible and (self.is_supervisor or self.is_admin)
