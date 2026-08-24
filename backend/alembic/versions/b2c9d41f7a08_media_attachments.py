"""media attachments on requests and messages

Turns ``request_attachments`` from a photo table into a general media table, and lets an
attachment hang off a single message rather than only off the request. Telegram's file
handles are stored alongside our own copy so the bot can re-send a voice note or a round
video as that kind of media instead of re-uploading a downloaded file.

``request_messages.body`` becomes nullable: a voice message is a complete message with no
text at all.

Revision ID: b2c9d41f7a08
Revises: e4ba139f47ac
Create Date: 2026-08-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c9d41f7a08"
down_revision: str | None = "e4ba139f47ac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "request_attachments",
        # Existing rows are all bot photo uploads, so the backfill default is exact.
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="photo"),
    )
    # The default existed only to fill in the rows already there. Leaving it would make
    # "photo" the silent answer for every future insert that forgets to say what it is.
    op.alter_column("request_attachments", "kind", server_default=None)
    op.add_column(
        "request_attachments", sa.Column("message_id", sa.BigInteger(), nullable=True)
    )
    op.add_column("request_attachments", sa.Column("file_size", sa.BigInteger(), nullable=True))
    op.add_column(
        "request_attachments", sa.Column("duration_seconds", sa.Integer(), nullable=True)
    )
    op.add_column(
        "request_attachments", sa.Column("telegram_file_id", sa.String(length=256), nullable=True)
    )
    op.add_column(
        "request_attachments",
        sa.Column("telegram_file_unique_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_request_attachments_message_id", "request_attachments", ["message_id"], unique=False
    )
    op.create_foreign_key(
        "fk_request_attachments_message_id",
        "request_attachments",
        "request_messages",
        ["message_id"],
        ["id"],
    )
    # A file we could not download (over the Bot API's 20 MB ceiling) still has a usable
    # Telegram handle, so a missing local copy must be representable.
    op.alter_column("request_attachments", "file_path", existing_type=sa.String(), nullable=True)

    op.alter_column("request_messages", "body", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("request_messages", "body", existing_type=sa.Text(), nullable=False)

    op.alter_column("request_attachments", "file_path", existing_type=sa.String(), nullable=False)
    op.drop_constraint(
        "fk_request_attachments_message_id", "request_attachments", type_="foreignkey"
    )
    op.drop_index("ix_request_attachments_message_id", table_name="request_attachments")
    op.drop_column("request_attachments", "telegram_file_unique_id")
    op.drop_column("request_attachments", "telegram_file_id")
    op.drop_column("request_attachments", "duration_seconds")
    op.drop_column("request_attachments", "file_size")
    op.drop_column("request_attachments", "message_id")
    op.drop_column("request_attachments", "kind")
