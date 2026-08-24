"""group broadcast and co-assignees

Three things the RTM group flow needs:

* ``notification_chats`` — which Telegram groups the bot broadcasts into.
* ``request_group_posts`` — the card message per request per group, so the same message can
  be edited as the request progresses instead of the group filling with updates.
* ``request_assignees`` — several staff on one request, with one of them marked primary.
  Backfilled from ``requests.assigned_to_employee_id``, which stays as the primary.

``ratings`` loses its one-row-per-request constraint: with several assignees, one act of
rating credits each of them.

Revision ID: c73e5a19b204
Revises: b2c9d41f7a08
Create Date: 2026-08-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c73e5a19b204"
down_revision: str | None = "b2c9d41f7a08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_chats",
        sa.Column("chat_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("chat_type", sa.String(length=24), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "registered_by_employee_id",
            sa.BigInteger(),
            sa.ForeignKey("employees.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notification_chats_is_active", "notification_chats", ["is_active"], unique=False
    )

    op.create_table(
        "request_group_posts",
        sa.Column(
            "request_id", sa.BigInteger(), sa.ForeignKey("requests.id"), primary_key=True
        ),
        sa.Column("chat_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "request_assignees",
        sa.Column(
            "request_id", sa.BigInteger(), sa.ForeignKey("requests.id"), primary_key=True
        ),
        sa.Column(
            "employee_id", sa.BigInteger(), sa.ForeignKey("employees.id"), primary_key=True
        ),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("assigned_by_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_request_assignees_employee_id", "request_assignees", ["employee_id"], unique=False
    )

    # Every request that already has an assignee becomes a one-person assignment, so the
    # new "my work" queries return the same results on day one as the old column did.
    op.execute(
        """
        INSERT INTO request_assignees (request_id, employee_id, is_primary, assigned_by_user_id, assigned_at)
        SELECT id, assigned_to_employee_id, TRUE, assigned_by_user_id,
               COALESCE(assigned_at, created_at)
        FROM requests
        WHERE assigned_to_employee_id IS NOT NULL
        """
    )

    # The old constraint was declared without a name, so Postgres generated one. Looking it
    # up beats hard-coding the generated name, which differs if the table was ever rebuilt.
    op.execute(
        """
        DO $$
        DECLARE constraint_name text;
        BEGIN
            SELECT con.conname INTO constraint_name
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = con.conkey[1]
            WHERE rel.relname = 'ratings'
              AND con.contype = 'u'
              AND array_length(con.conkey, 1) = 1
              AND att.attname = 'request_id';
            IF constraint_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE ratings DROP CONSTRAINT %I', constraint_name);
            END IF;
        END $$;
        """
    )
    op.create_unique_constraint(
        "uq_ratings_request_employee", "ratings", ["request_id", "rated_employee_id"]
    )
    # The dropped unique constraint was also the only index on this column, and every
    # rating lookup is by request.
    op.create_index("ix_ratings_request_id", "ratings", ["request_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ratings_request_id", table_name="ratings")
    op.drop_constraint("uq_ratings_request_employee", "ratings", type_="unique")
    op.create_unique_constraint("ratings_request_id_key", "ratings", ["request_id"])
    op.drop_index("ix_request_assignees_employee_id", table_name="request_assignees")
    op.drop_table("request_assignees")
    op.drop_table("request_group_posts")
    op.drop_index("ix_notification_chats_is_active", table_name="notification_chats")
    op.drop_table("notification_chats")
