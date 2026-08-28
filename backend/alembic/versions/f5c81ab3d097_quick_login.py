"""Quick login: an employee id number plus a local password

HEMIS moved its own sign-in behind One-ID. Most staff have not linked their profile to it
and cannot remember the password, so the OAuth route — the only way in until now — locks
out the people it exists to admit. The roster is already in this database, so an employee
can identify themselves with their id number and a password they set here.

The columns below are that password, the address a forgotten one is mailed to, the reset
token (hashed), and a small lock so a list of id numbers cannot be walked with a guesser.

Revision ID: f5c81ab3d097
Revises: e93b17c40d52
Create Date: 2026-08-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f5c81ab3d097"
down_revision: str | None = "e93b17c40d52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("quick_password_hash", sa.String(128), nullable=True))
    op.add_column("employees", sa.Column("recovery_email", sa.String(255), nullable=True))
    op.add_column(
        "employees", sa.Column("password_set_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "employees", sa.Column("password_reset_token_hash", sa.String(64), nullable=True)
    )
    op.add_column(
        "employees", sa.Column("password_reset_sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "employees",
        sa.Column("password_reset_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "employees",
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "employees", sa.Column("login_locked_until", sa.DateTime(timezone=True), nullable=True)
    )
    # The reset link is looked up by token and nothing else, so it needs its own index.
    op.create_index(
        "ix_employees_password_reset_token_hash", "employees", ["password_reset_token_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_employees_password_reset_token_hash", table_name="employees")
    for column in (
        "login_locked_until",
        "failed_login_count",
        "password_reset_expires_at",
        "password_reset_sent_at",
        "password_reset_token_hash",
        "password_set_at",
        "recovery_email",
        "quick_password_hash",
    ):
        op.drop_column("employees", column)
