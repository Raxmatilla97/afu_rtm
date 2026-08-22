"""Idempotently seed the default request categories. Safe to re-run."""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.db import session_scope
from afu_shared.models import Category

CATEGORIES: list[tuple[str, str, int]] = [
    ("printer", "Printer/skaner muammosi", 10),
    ("software", "Dasturiy ta'minot o'rnatish/sozlash", 20),
    ("network", "Tarmoq/internet muammosi", 30),
    ("hardware", "Kompyuter texnik nosozligi", 40),
    ("account", "Foydalanuvchi hisobi (login/parol) muammosi", 50),
    ("email", "Elektron pochta muammosi", 60),
    ("av_equipment", "Proyektor/audio-video uskunalari muammosi", 70),
    ("telephony", "IP-telefoniya muammosi", 80),
    ("website", "Universitet veb-sayti/portali muammosi", 90),
    ("new_equipment", "Yangi uskuna/jihoz so'rovi", 100),
    ("cabling", "Tarmoq kabeli ulanish ishlari", 110),
    ("other", "Boshqa muammo", 999),
]


async def seed_categories(session: AsyncSession) -> None:
    existing = {row.slug: row for row in (await session.execute(select(Category))).scalars()}
    for slug, label_uz, sort_order in CATEGORIES:
        if slug in existing:
            existing[slug].label_uz = label_uz
            existing[slug].sort_order = sort_order
            existing[slug].is_active = True
        else:
            session.add(Category(slug=slug, label_uz=label_uz, sort_order=sort_order, is_active=True))


async def main() -> None:
    async with session_scope() as session:
        await seed_categories(session)
    print(f"Seeded {len(CATEGORIES)} categories.")


if __name__ == "__main__":
    asyncio.run(main())
