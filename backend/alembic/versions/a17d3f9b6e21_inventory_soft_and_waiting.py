"""RTM inventory, RTM soft, and the waiting status

Three things that arrived together because they answer one question — what stops a request
being finished today:

* ``inventory_*`` — what is on the shelf, and the movement rows that explain how it got
  there. Stock is never edited directly; the quantity is the sum of its movements.
* ``soft_*`` — the driver and software shelf the bot hands out.
* ``requests.waiting_until`` / ``waiting_reason`` plus the ``waiting`` status — a request
  blocked on a part nobody has yet.

Revision ID: a17d3f9b6e21
Revises: f04c8b2e5a17
Create Date: 2026-08-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a17d3f9b6e21"
down_revision: str | None = "f04c8b2e5a17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Seeded so the register is usable the moment it is deployed. An empty category list makes
#: the bot's "which category?" step a dead end, and the first RTM staffer to hit it has no
#: way forward.
INVENTORY_CATEGORIES = [
    ("toner", "🖨 Toner va kartrij", 10),
    ("printer-parts", "⚙️ Printer ehtiyot qismlari", 20),
    ("cable", "🔌 Kabel va ulagichlar", 30),
    ("network", "🌐 Tarmoq uskunalari", 40),
    ("computer-parts", "💻 Kompyuter qismlari", 50),
    ("peripherals", "🖱 Periferiya (sichqoncha, klaviatura)", 60),
    ("storage", "💾 Xotira va disklar", 70),
    ("consumables", "📦 Boshqa rasxodniklar", 80),
    ("tools", "🧰 Asboblar", 90),
    ("other", "➕ Boshqa", 100),
]

SOFT_CATEGORIES = [
    ("drivers-printer", "🖨 Printer drayverlari", 10),
    ("drivers-network", "🌐 Tarmoq drayverlari", 20),
    ("drivers-other", "⚙️ Boshqa drayverlar", 30),
    ("os", "💿 Operatsion tizimlar", 40),
    ("office", "📄 Ofis dasturlari", 50),
    ("antivirus", "🛡 Antivirus", 60),
    ("utilities", "🧰 Yordamchi dasturlar", 70),
    ("other", "➕ Boshqa", 100),
]


def upgrade() -> None:
    op.add_column("requests", sa.Column("waiting_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("requests", sa.Column("waiting_reason", sa.Text(), nullable=True))

    op.create_table(
        "inventory_categories",
        sa.Column("slug", sa.String(length=40), primary_key=True),
        sa.Column("label_uz", sa.String(length=120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "inventory_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "category_slug",
            sa.String(length=40),
            sa.ForeignKey("inventory_categories.slug"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("unit", sa.String(length=24), nullable=False, server_default="dona"),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("min_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="available"),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_inventory_items_category_slug", "inventory_items", ["category_slug"])
    op.create_index("ix_inventory_items_status", "inventory_items", ["status"])

    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "item_id", sa.BigInteger(), sa.ForeignKey("inventory_items.id"), nullable=False
        ),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.BigInteger(), sa.ForeignKey("requests.id"), nullable=True),
        sa.Column("employee_id", sa.BigInteger(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_inventory_movements_item_id", "inventory_movements", ["item_id"])
    op.create_index("ix_inventory_movements_request_id", "inventory_movements", ["request_id"])
    op.create_index("ix_inventory_movements_reason", "inventory_movements", ["reason"])
    op.create_index("ix_inventory_movements_created_at", "inventory_movements", ["created_at"])

    op.create_table(
        "inventory_attachments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "item_id", sa.BigInteger(), sa.ForeignKey("inventory_items.id"), nullable=False
        ),
        sa.Column(
            "movement_id", sa.BigInteger(), sa.ForeignKey("inventory_movements.id"), nullable=True
        ),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=True),
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "uploaded_by_employee_id",
            sa.BigInteger(),
            sa.ForeignKey("employees.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_inventory_attachments_item_id", "inventory_attachments", ["item_id"])
    op.create_index(
        "ix_inventory_attachments_movement_id", "inventory_attachments", ["movement_id"]
    )

    op.create_table(
        "soft_categories",
        sa.Column("slug", sa.String(length=40), primary_key=True),
        sa.Column("label_uz", sa.String(length=120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "soft_assets",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "category_slug",
            sa.String(length=40),
            sa.ForeignKey("soft_categories.slug"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.String(length=64), nullable=True),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=True),
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("telegram_file_id", sa.String(length=256), nullable=True),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("uploaded_by_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "uploaded_by_employee_id",
            sa.BigInteger(),
            sa.ForeignKey("employees.id"),
            nullable=True,
        ),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_soft_assets_category_slug", "soft_assets", ["category_slug"])
    op.create_index("ix_soft_assets_is_active", "soft_assets", ["is_active"])

    inventory = sa.table(
        "inventory_categories",
        sa.column("slug", sa.String),
        sa.column("label_uz", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        inventory,
        [{"slug": s, "label_uz": label, "sort_order": order} for s, label, order in INVENTORY_CATEGORIES],
    )

    soft = sa.table(
        "soft_categories",
        sa.column("slug", sa.String),
        sa.column("label_uz", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        soft,
        [{"slug": s, "label_uz": label, "sort_order": order} for s, label, order in SOFT_CATEGORIES],
    )


def downgrade() -> None:
    op.drop_index("ix_soft_assets_is_active", table_name="soft_assets")
    op.drop_index("ix_soft_assets_category_slug", table_name="soft_assets")
    op.drop_table("soft_assets")
    op.drop_table("soft_categories")

    op.drop_index("ix_inventory_attachments_movement_id", table_name="inventory_attachments")
    op.drop_index("ix_inventory_attachments_item_id", table_name="inventory_attachments")
    op.drop_table("inventory_attachments")

    for index in (
        "ix_inventory_movements_created_at",
        "ix_inventory_movements_reason",
        "ix_inventory_movements_request_id",
        "ix_inventory_movements_item_id",
    ):
        op.drop_index(index, table_name="inventory_movements")
    op.drop_table("inventory_movements")

    op.drop_index("ix_inventory_items_status", table_name="inventory_items")
    op.drop_index("ix_inventory_items_category_slug", table_name="inventory_items")
    op.drop_table("inventory_items")
    op.drop_table("inventory_categories")

    # Anything parked in "waiting" has to land somewhere the old code understands.
    op.execute("UPDATE requests SET status = 'in_progress' WHERE status = 'waiting'")
    op.drop_column("requests", "waiting_reason")
    op.drop_column("requests", "waiting_until")
