"""hemis oauth and bot ux

Adds the HEMIS OAuth2 identity columns to ``employees`` and the ``oauth_login_attempts``
table that stores the OAuth state, the flow context, and the full userinfo payload used to
diagnose logins that fail to match a local employee.

Revision ID: e4ba139f47ac
Revises: f78ab39c10e6
Create Date: 2026-08-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e4ba139f47ac"
down_revision: str | None = "f78ab39c10e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("hemis_oauth_subject", sa.String(length=64), nullable=True))
    op.add_column("employees", sa.Column("hemis_uuid", sa.String(length=64), nullable=True))
    op.add_column("employees", sa.Column("hemis_login", sa.String(length=128), nullable=True))
    op.add_column("employees", sa.Column("hemis_email", sa.String(length=255), nullable=True))
    op.add_column("employees", sa.Column("hemis_phone", sa.String(length=32), nullable=True))
    op.add_column("employees", sa.Column("hemis_university_id", sa.String(length=64), nullable=True))
    op.add_column(
        "employees", sa.Column("oauth_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_employees_hemis_oauth_subject", "employees", ["hemis_oauth_subject"], unique=True
    )
    op.create_index("ix_employees_hemis_uuid", "employees", ["hemis_uuid"], unique=False)
    op.create_index("ix_employees_hemis_login", "employees", ["hemis_login"], unique=False)
    op.create_index(
        "ix_employees_hemis_university_id", "employees", ["hemis_university_id"], unique=False
    )

    op.create_table(
        "oauth_login_attempts",
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("flow", sa.String(length=16), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("next_path", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("match_strategy", sa.String(length=40), nullable=True),
        sa.Column("matched_employee_id", sa.BigInteger(), nullable=True),
        sa.Column("userinfo_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["matched_employee_id"], ["employees.id"]),
        sa.PrimaryKeyConstraint("state"),
    )
    op.create_index(
        "ix_oauth_login_attempts_telegram_user_id",
        "oauth_login_attempts",
        ["telegram_user_id"],
        unique=False,
    )
    op.create_index("ix_oauth_login_attempts_status", "oauth_login_attempts", ["status"], unique=False)
    op.create_index(
        "ix_oauth_login_attempts_matched_employee_id",
        "oauth_login_attempts",
        ["matched_employee_id"],
        unique=False,
    )
    op.create_index(
        "ix_oauth_login_attempts_expires_at", "oauth_login_attempts", ["expires_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_oauth_login_attempts_expires_at", table_name="oauth_login_attempts")
    op.drop_index("ix_oauth_login_attempts_matched_employee_id", table_name="oauth_login_attempts")
    op.drop_index("ix_oauth_login_attempts_status", table_name="oauth_login_attempts")
    op.drop_index("ix_oauth_login_attempts_telegram_user_id", table_name="oauth_login_attempts")
    op.drop_table("oauth_login_attempts")

    op.drop_index("ix_employees_hemis_university_id", table_name="employees")
    op.drop_index("ix_employees_hemis_login", table_name="employees")
    op.drop_index("ix_employees_hemis_uuid", table_name="employees")
    op.drop_index("ix_employees_hemis_oauth_subject", table_name="employees")
    op.drop_column("employees", "oauth_verified_at")
    op.drop_column("employees", "hemis_university_id")
    op.drop_column("employees", "hemis_phone")
    op.drop_column("employees", "hemis_email")
    op.drop_column("employees", "hemis_login")
    op.drop_column("employees", "hemis_uuid")
    op.drop_column("employees", "hemis_oauth_subject")
