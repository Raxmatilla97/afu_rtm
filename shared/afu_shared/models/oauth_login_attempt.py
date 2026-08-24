from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afu_shared.enums import OAuthAttemptStatus
from afu_shared.models.base import Base
from afu_shared.models.employee import Employee


class OAuthLoginAttempt(Base):
    """One row per HEMIS OAuth login attempt.

    Serves three jobs at once:
      1. CSRF/state store for the authorization-code flow (``state`` is the primary key),
      2. flow context carried across the redirect (which Telegram user started a bot login,
         where a web login should land afterwards),
      3. the diagnostic record — ``userinfo_json`` is always persisted, so a login that fails
         to match an employee can be diagnosed from the row alone.
    """

    __tablename__ = "oauth_login_attempts"

    state: Mapped[str] = mapped_column(String(64), primary_key=True)

    flow: Mapped[str] = mapped_column(String(16), nullable=False)

    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    #: Web flow only: the SPA path to redirect to after a successful login.
    next_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=OAuthAttemptStatus.PENDING.value, index=True
    )
    #: Which rung of the matching cascade resolved the employee.
    match_strategy: Mapped[str | None] = mapped_column(String(40), nullable=True)
    matched_employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=True, index=True
    )
    matched_employee: Mapped["Employee | None"] = relationship("Employee")

    #: Full userinfo payload, always stored — this is what makes an unmatched login diagnosable.
    userinfo_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<OAuthLoginAttempt state={self.state[:8]!r}… flow={self.flow!r} status={self.status!r}>"
