"""record when an overdue warning was sent

The overdue sweep runs on a schedule. Without somewhere to record that a request has
already been warned about, every pass would warn again — and a warning that arrives every
half hour is one people stop reading.

Revision ID: d81f4c60a7e3
Revises: c73e5a19b204
Create Date: 2026-08-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d81f4c60a7e3"
down_revision: str | None = "c73e5a19b204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "requests", sa.Column("overdue_notified_at", sa.DateTime(timezone=True), nullable=True)
    )
    # The sweep looks for open requests whose deadline has passed and that have not been
    # warned yet. Partial, because everything else in the table is irrelevant to it.
    op.create_index(
        "ix_requests_overdue_scan",
        "requests",
        ["deadline_at"],
        unique=False,
        postgresql_where=sa.text(
            "deadline_at IS NOT NULL AND status IN ('new', 'assigned', 'in_progress')"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_requests_overdue_scan", table_name="requests")
    op.drop_column("requests", "overdue_notified_at")
