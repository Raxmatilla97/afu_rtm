"""Requests filed as a management directive

One additive column: ``requests.requester_role``.

A Boshliq (and an Admin who is also one) can now file a request that already carries a
deadline and a team, and the RTM group has to be able to tell such a directive apart from
an ordinary fault report before reading a word of it. The role is stamped at creation
rather than read back off the requester's flags, because a group card is edited in place
for the request's whole life — deriving it would mean a demotion silently rewrote every
directive that person ever issued.

Revision ID: c4f10d8b73a2
Revises: b6e1c94af205
Create Date: 2026-09-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4f10d8b73a2"
down_revision: str | None = "b6e1c94af205"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("requester_role", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("requests", "requester_role")
