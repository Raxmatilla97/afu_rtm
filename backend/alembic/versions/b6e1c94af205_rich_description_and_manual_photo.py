"""Rich request descriptions and hand-uploaded employee photos

Two columns, both additive:

* ``requests.description_html`` — the formatted description the web form now produces.
  ``description`` stays exactly what it was, the plain reading, because every Telegram
  surface escapes it; markup stored there would reach RTM staff as literal ``<p>`` tags.
* ``employees.image_manual_at`` — when a photo was uploaded by hand. The HEMIS sync
  re-downloads a portrait whenever the offered URL differs from the recorded one, which
  for an uploaded picture is always true, so without this marker the next sync would
  quietly overwrite it.

Revision ID: b6e1c94af205
Revises: a7d4e2f19b83
Create Date: 2026-08-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6e1c94af205"
down_revision: str | None = "a7d4e2f19b83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("description_html", sa.Text(), nullable=True))
    op.add_column(
        "employees",
        sa.Column("image_manual_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("employees", "image_manual_at")
    op.drop_column("requests", "description_html")
