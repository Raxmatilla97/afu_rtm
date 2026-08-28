"""Settings an administrator can change without a deploy.

Two of them so far: the site's own descriptive text (title, description, keywords) and the
outgoing mail server. Both were environment variables, which means changing either one used
to require somebody with SSH access, a text editor and a container rebuild — for a mail
password that expired on a Sunday.

One row per group, with the values as JSON, because these are small documents rather than
tables: the alternative is a column per field and a migration every time the panel grows
another checkbox.

The environment variables stay as the fallback. A row here overrides them, so an
installation that has never opened the settings page behaves exactly as it did before.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from afu_shared.models.base import Base

#: The site's own descriptive text — browser tab title, meta description, keywords.
KEY_SITE = "site"
#: Outgoing mail. Overrides SMTP_* from the environment when present.
KEY_SMTP = "smtp"


class SiteSetting(Base):
    __tablename__ = "site_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    updated_by_employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<SiteSetting {self.key!r}>"
