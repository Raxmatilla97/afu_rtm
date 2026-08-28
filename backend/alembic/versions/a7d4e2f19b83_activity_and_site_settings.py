"""Activity log and editable site settings

Two tables behind the admin panel's new "Sozlamalar va kuzatuv" page:

* ``activity_events`` — who did what, and when. Nothing else in the database could answer
  "is anybody using the bot today?": requests and messages record outcomes, while opening
  the bot, reading your tasks and closing it leaves no trace at all.
* ``site_settings`` — the descriptive text and the mail server, as JSON documents that an
  administrator can edit instead of an environment variable somebody has to SSH in to
  change.

Revision ID: a7d4e2f19b83
Revises: f5c81ab3d097
Create Date: 2026-08-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7d4e2f19b83"
down_revision: str | None = "f5c81ab3d097"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_name", sa.String(length=200), nullable=True),
        sa.Column("target", sa.String(length=200), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
    )
    op.create_index("ix_activity_events_created_at", "activity_events", ["created_at"])
    op.create_index("ix_activity_events_source", "activity_events", ["source"])
    op.create_index("ix_activity_events_action", "activity_events", ["action"])
    op.create_index("ix_activity_events_employee_id", "activity_events", ["employee_id"])
    # The daily-active-users query counts distinct people per day per source, and the feed
    # is always newest-first. Both walk this pair, so it gets its own index.
    op.create_index(
        "ix_activity_events_source_created_at", "activity_events", ["source", "created_at"]
    )

    op.create_table(
        "site_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "updated_by_employee_id", sa.BigInteger(), sa.ForeignKey("employees.id"), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_table("site_settings")
    for index in (
        "ix_activity_events_source_created_at",
        "ix_activity_events_employee_id",
        "ix_activity_events_action",
        "ix_activity_events_source",
        "ix_activity_events_created_at",
    ):
        op.drop_index(index, table_name="activity_events")
    op.drop_table("activity_events")
