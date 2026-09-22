"""Log of what the bot has posted into the RTM groups

One new table, ``group_messages``. Until now only request cards were remembered — every
other message the bot sent to a group (the reply line when somebody took a job, the overdue
alarm, the welcome notice, files replayed by the 📎 button) was fire-and-forget, so the
admin panel could not answer "what is the bot showing the group right now, and can you take
that one down".

Deliberately separate from ``request_group_posts``, which stays the one row per request that
the worker edits in place. Merging them would mean writing one Telegram message id in two
places, and the panel unions the two queries instead.

Revision ID: d6b2e94c31f8
Revises: c4f10d8b73a2
Create Date: 2026-09-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6b2e94c31f8"
down_revision: str | None = "c4f10d8b73a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "group_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.BigInteger(), nullable=True),
        sa.Column("preview", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["chat_id"], ["notification_chats.chat_id"]),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        # One row per Telegram message: makes the delete path idempotent and stops a retried
        # worker job from logging the same post twice.
        sa.UniqueConstraint("chat_id", "message_id", name="uq_group_messages_chat_message"),
    )
    op.create_index("ix_group_messages_chat_id", "group_messages", ["chat_id"])
    op.create_index("ix_group_messages_kind", "group_messages", ["kind"])
    op.create_index("ix_group_messages_request_id", "group_messages", ["request_id"])
    op.create_index("ix_group_messages_created_at", "group_messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_group_messages_created_at", table_name="group_messages")
    op.drop_index("ix_group_messages_request_id", table_name="group_messages")
    op.drop_index("ix_group_messages_kind", table_name="group_messages")
    op.drop_index("ix_group_messages_chat_id", table_name="group_messages")
    op.drop_table("group_messages")
