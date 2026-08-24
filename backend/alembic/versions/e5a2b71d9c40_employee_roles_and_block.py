"""employee roles and manual block

Adds the two roles the group flow needs — supervisor ("Boshliq") and employee-level admin —
plus a manual block flag.

The block is a new column rather than a reuse of ``access_revoked``: that one belongs to the
HEMIS sync, which clears it again for anybody HEMIS still reports as active. A ban stored
there would undo itself on the next import.

Revision ID: e5a2b71d9c40
Revises: d81f4c60a7e3
Create Date: 2026-08-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5a2b71d9c40"
down_revision: str | None = "d81f4c60a7e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("is_supervisor", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "employees",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "employees",
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("employees", sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "blocked_at")
    op.drop_column("employees", "is_blocked")
    op.drop_column("employees", "is_admin")
    op.drop_column("employees", "is_supervisor")
