"""a HEMIS sync run can be started by an employee-admin

Employees flagged Admin now hold real admin-panel powers, and that includes running the
HEMIS import. The run has to record who started it, and the only column available pointed
at ``users`` — the email/password panel account, which an employee-admin does not have.

Revision ID: f04c8b2e5a17
Revises: e5a2b71d9c40
Create Date: 2026-08-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f04c8b2e5a17"
down_revision: str | None = "e5a2b71d9c40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "hemis_sync_runs", "triggered_by_user_id", existing_type=sa.BigInteger(), nullable=True
    )
    op.add_column(
        "hemis_sync_runs", sa.Column("triggered_by_employee_id", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        "fk_hemis_sync_runs_triggered_by_employee_id",
        "hemis_sync_runs",
        "employees",
        ["triggered_by_employee_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_hemis_sync_runs_triggered_by_employee_id", "hemis_sync_runs", type_="foreignkey"
    )
    op.drop_column("hemis_sync_runs", "triggered_by_employee_id")
    # A run started by an employee has no user to point at, so it cannot survive the column
    # becoming NOT NULL again.
    op.execute("DELETE FROM hemis_sync_runs WHERE triggered_by_user_id IS NULL")
    op.alter_column(
        "hemis_sync_runs", "triggered_by_user_id", existing_type=sa.BigInteger(), nullable=False
    )
