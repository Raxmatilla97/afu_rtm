"""Demo rows for RTM Inventar and RTM Soft — seeded exactly once

A one-time data load, deliberately written as a migration rather than as a seed script.

The seed scripts in ``backend/scripts`` run on every container start and are written to be
idempotent, which is right for categories and the admin account: those must exist, and
re-asserting them is harmless. Demo rows are the opposite — they exist to be looked at,
then deleted and replaced with real data. A start-up seeder would put them back on the next
deploy, so the register could never be emptied.

Alembic already answers "has this run on this database?" and never runs a revision twice,
which is exactly the guarantee needed here. Delete every row this adds and nothing brings
them back.

Revision ID: c1f7a9d24b30
Revises: a17d3f9b6e21
Create Date: 2026-08-25

"""

import logging
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

from afu_shared.settings import settings

revision: str = "c1f7a9d24b30"
down_revision: str | None = "a17d3f9b6e21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

#: Every row this migration writes carries it, so ``downgrade`` can find its own work and
#: nothing else — a real toner somebody typed in by hand must survive a rollback.
DEMO_MARK = "Demo:"

#: (category_slug, name, unit, quantity, min_quantity, unit_price, note)
#:
#: Chosen to show the register doing its job rather than to be a plausible warehouse: one
#: line sits below its minimum so the "Tugayapti" tile is not stuck at zero, and the
#: planned line below has no stock at all so "Rejada" means something too.
DEMO_ITEMS: list[tuple[str, str, str, int, int, str, str]] = [
    ("toner", "HP 85A (CE285A) toner kartrij", "dona", 12, 4, "320000.00", "2-qavat ombori"),
    ("toner", "Canon 737 toner kartrij", "dona", 6, 3, "285000.00", "Dekanat printerlari uchun"),
    ("printer-parts", "HP LaserJet P1102 uchun fotoval", "dona", 4, 2, "95000.00", "Zaxira qism"),
    ("cable", "UTP Cat5e tarmoq kabeli", "metr", 300, 50, "4500.00", "Buxta, 305 metrlik"),
    ("cable", "HDMI kabel 3 m", "dona", 8, 3, "55000.00", "Auditoriya proyektorlari uchun"),
    ("network", "TP-Link TL-SG1008D 8-portli switch", "dona", 1, 2, "480000.00", "Qoldiq kam"),
    ("computer-parts", "Kingston DDR4 8GB 2666 MHz", "dona", 10, 4, "410000.00", "Xotira moduli"),
    ("peripherals", "A4Tech OP-720 USB sichqoncha", "dona", 15, 5, "65000.00", "Ish stollari uchun"),
    (
        "storage",
        "Kingston A400 SSD 480 GB",
        "dona",
        5,
        2,
        "520000.00",
        "Eski kompyuterlarni tezlatish uchun",
    ),
]

#: Stock that has not arrived yet: no movement row, quantity stays 0, status "planned".
DEMO_PLANNED: tuple[str, str, str, int, str, str] = (
    "network",
    "Wi-Fi router TP-Link Archer C6",
    "dona",
    1,
    "690000.00",
    "Rejada, hali xarid qilinmagan",
)

#: (category_slug, title, version, filename)
DEMO_SOFT: list[tuple[str, str, str, str]] = [
    ("drivers-printer", "HP LaserJet P1102 drayver", "Win 10/11 x64", "hp-laserjet-p1102.txt"),
    ("drivers-printer", "Canon LBP2900B drayver", "Win 10 x64", "canon-lbp2900b.txt"),
    ("drivers-printer", "Kyocera ECOSYS universal drayver", "Win 7/10/11", "kyocera-ecosys.txt"),
    (
        "drivers-network",
        "TP-Link TL-WN725N Wi-Fi adapter drayveri",
        "Win 10/11",
        "tp-link-wn725n.txt",
    ),
    ("drivers-other", "Realtek HD Audio drayver", "Win 10/11 x64", "realtek-hd-audio.txt"),
    ("os", "Windows 11 o'rnatish qo'llanmasi", "23H2", "windows-11-qollanma.txt"),
    ("office", "LibreOffice o'rnatish to'plami", "7.6", "libreoffice-7-6.txt"),
    ("antivirus", "Kaspersky Free o'rnatish fayli", "21.3", "kaspersky-free.txt"),
    ("utilities", "7-Zip arxivator", "23.01", "7zip-23-01.txt"),
    ("utilities", "AnyDesk masofaviy ulanish", "8.0", "anydesk-8.txt"),
]

DEMO_SOFT_DESCRIPTION = "namuna yozuv, haqiqiy fayl bilan almashtiring"

#: A demo asset needs a file on disk or its download button 404s. A short note in the
#: interface language beats an empty file: whoever opens it learns what to do with the row.
PLACEHOLDER_TEMPLATE = (
    "{title}\n"
    "{underline}\n\n"
    "Bu — namuna (demo) fayl. RTM Soft bo'limi qanday ishlashini ko'rsatish uchun\n"
    "qo'yilgan. O'rniga haqiqiy drayver yoki dasturni yuklang: RTM Soft sahifasidagi\n"
    "«Fayl yuklash» tugmasi orqali yangisini qo'shing va bu yozuvni yashiring.\n"
)


def _placeholder(title: str) -> bytes:
    return PLACEHOLDER_TEMPLATE.format(title=title, underline="=" * len(title)).encode("utf-8")


def upgrade() -> None:
    conn = op.get_bind()

    insert_item = sa.text(
        """
        INSERT INTO inventory_items
            (category_slug, name, unit, quantity, min_quantity, status, unit_price, note)
        VALUES
            (:category_slug, :name, :unit, :quantity, :min_quantity, :status, :unit_price, :note)
        RETURNING id
        """
    )
    # Written as SQL rather than through afu_shared.inventory: a migration has to keep
    # working when the application code around it moves on. The invariant it upholds is the
    # one that module exists for — an item's quantity is the sum of its movements — so
    # every seeded quantity arrives as a purchase instead of a number typed into the item.
    insert_movement = sa.text(
        """
        INSERT INTO inventory_movements (item_id, delta, reason, unit_price, note)
        VALUES (:item_id, :delta, 'purchase', :unit_price, :note)
        """
    )

    for category_slug, name, unit, quantity, min_quantity, unit_price, note in DEMO_ITEMS:
        item_id = conn.execute(
            insert_item,
            {
                "category_slug": category_slug,
                "name": name,
                "unit": unit,
                "quantity": quantity,
                "min_quantity": min_quantity,
                "status": "available",
                "unit_price": unit_price,
                "note": f"{DEMO_MARK} {note}",
            },
        ).scalar_one()
        conn.execute(
            insert_movement,
            {
                "item_id": item_id,
                "delta": quantity,
                "unit_price": unit_price,
                "note": f"{DEMO_MARK} boshlang'ich qoldiq",
            },
        )

    planned_category, planned_name, planned_unit, planned_min, planned_price, planned_note = (
        DEMO_PLANNED
    )
    conn.execute(
        insert_item,
        {
            "category_slug": planned_category,
            "name": planned_name,
            "unit": planned_unit,
            "quantity": 0,
            "min_quantity": planned_min,
            "status": "planned",
            "unit_price": planned_price,
            "note": f"{DEMO_MARK} {planned_note}",
        },
    )

    insert_asset = sa.text(
        """
        INSERT INTO soft_assets
            (category_slug, title, description, version, file_path, original_filename,
             content_type, file_size)
        VALUES
            (:category_slug, :title, :description, :version, :file_path, :original_filename,
             'text/plain', :file_size)
        """
    )
    storage_root = Path(settings.storage_root)

    for category_slug, title, version, filename in DEMO_SOFT:
        payload = _placeholder(title)
        stored = f"demo-{filename}"
        try:
            target_dir = storage_root / "soft" / category_slug
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / stored).write_bytes(payload)
        except OSError as exc:
            # The row is still worth having — it fills the page and the bot menu. Only the
            # download misses, and it misses with "Fayl topilmadi" rather than taking a
            # whole deploy down over a demo text file.
            logger.warning("Could not write the demo soft file %s: %s", stored, exc)

        conn.execute(
            insert_asset,
            {
                "category_slug": category_slug,
                "title": title,
                "description": f"{DEMO_MARK} {DEMO_SOFT_DESCRIPTION}",
                "version": version,
                "file_path": f"soft/{category_slug}/{stored}",
                "original_filename": stored,
                "file_size": len(payload),
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    mark = f"{DEMO_MARK}%"

    # Movements first — they hold the foreign key. Scoped to demo items only: a real
    # consumption booked against one of them would be somebody's actual work.
    conn.execute(
        sa.text(
            "DELETE FROM inventory_movements WHERE item_id IN "
            "(SELECT id FROM inventory_items WHERE note LIKE :mark)"
        ),
        {"mark": mark},
    )
    conn.execute(sa.text("DELETE FROM inventory_items WHERE note LIKE :mark"), {"mark": mark})
    conn.execute(sa.text("DELETE FROM soft_assets WHERE description LIKE :mark"), {"mark": mark})
