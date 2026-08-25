"""How many times a soft asset was seen, next to how many times it was taken

``download_count`` alone cannot tell a file nobody wants from one nobody has found. The
bot's Soft list is where people actually browse the shelf, so every asset shown on a
rendered page counts as one view there.

Revision ID: d2a4c8e10f37
Revises: c1f7a9d24b30
Create Date: 2026-08-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2a4c8e10f37"
down_revision: str | None = "c1f7a9d24b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "soft_assets",
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("soft_assets", "view_count")
