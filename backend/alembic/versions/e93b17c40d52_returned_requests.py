"""Sending a wrongly filed request back, with the reason attached

A Boshliq or Admin can return a request instead of assigning it: wrong department, not
enough detail to act on, a duplicate. The new ``returned`` status is deliberately not
``cancelled`` — cancelled is the reporter giving up on work RTM accepted, while a returned
request never entered the queue at all, which is why the request list hides it by default
and offers it behind its own filter.

Revision ID: e93b17c40d52
Revises: d2a4c8e10f37
Create Date: 2026-08-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e93b17c40d52"
down_revision: str | None = "d2a4c8e10f37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("requests", sa.Column("return_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    # Anything sitting in "returned" has to land somewhere the old code understands, and
    # cancelled is the only closed state it has. Same shape as the waiting rollback.
    op.execute("UPDATE requests SET status = 'cancelled' WHERE status = 'returned'")
    op.drop_column("requests", "return_reason")
    op.drop_column("requests", "returned_at")
