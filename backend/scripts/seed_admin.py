"""Idempotently bootstrap the admin account from ADMIN_EMAIL/ADMIN_PASSWORD env vars. Safe to re-run."""

import asyncio

from sqlalchemy import select

from afu_shared.db import session_scope
from afu_shared.enums import UserRole
from afu_shared.models import User
from afu_shared.settings import settings
from app.security import hash_password


async def main() -> None:
    if not settings.admin_password:
        raise SystemExit("ADMIN_PASSWORD is not set; refusing to create an admin with no password.")

    async with session_scope() as session:
        existing = (
            await session.execute(select(User).where(User.email == settings.admin_email))
        ).scalar_one_or_none()

        if existing:
            existing.password_hash = hash_password(settings.admin_password)
            existing.is_active = True
            print(f"Updated existing admin: {settings.admin_email}")
        else:
            session.add(
                User(
                    email=settings.admin_email,
                    password_hash=hash_password(settings.admin_password),
                    role=UserRole.ADMIN.value,
                    is_active=True,
                )
            )
            print(f"Created admin: {settings.admin_email}")


if __name__ == "__main__":
    asyncio.run(main())
