"""Reading and writing the settings an administrator can change from the panel.

Layered on purpose: the environment variable is the default, and a row in ``site_settings``
overrides it. An installation that never opens the settings page keeps behaving exactly as
it did before, and one that fills the form in stops needing a deploy to change a mail
password.

The SMTP password is the one value that goes out of here only when something is about to
send a letter. Everything that answers an HTTP request uses :func:`smtp_config_public`,
which reports whether a password is stored without ever repeating it.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import KEY_SITE, KEY_SMTP, SiteSetting
from afu_shared.settings import settings

logger = logging.getLogger(__name__)

__all__ = [
    "KEY_SITE",
    "KEY_SMTP",
    "site_defaults",
    "get_group",
    "save_group",
    "site_config",
    "smtp_config",
    "smtp_config_public",
]


def site_defaults() -> dict[str, Any]:
    """What the site says about itself before anybody edits it."""
    return {
        "title": "RTM Murojaatlar tizimi",
        "description": (
            "Alfraganus University Raqamli texnologiyalar markazi — murojaatlarni qabul "
            "qilish va kuzatish tizimi."
        ),
        "keywords": "RTM, Alfraganus University, murojaat, texnik yordam, helpdesk",
        "organization": "Alfraganus University",
        "contact_email": "",
        "contact_phone": "",
    }


def _smtp_defaults() -> dict[str, Any]:
    return {
        "host": settings.smtp_host,
        "port": settings.smtp_port,
        "user": settings.smtp_user,
        "password": settings.smtp_password,
        "from_address": settings.smtp_from,
        "starttls": settings.smtp_starttls,
    }


async def get_group(session: AsyncSession, key: str) -> dict[str, Any]:
    row = await session.get(SiteSetting, key)
    return dict(row.value) if row and isinstance(row.value, dict) else {}


async def save_group(
    session: AsyncSession,
    key: str,
    value: dict[str, Any],
    *,
    user_id: int | None = None,
    employee_id: int | None = None,
) -> None:
    row = await session.get(SiteSetting, key)
    if row is None:
        row = SiteSetting(key=key, value={})
        session.add(row)
    # Merged rather than replaced: the SMTP form posts no password when it is unchanged,
    # and a straight overwrite would silently erase the stored one.
    merged = dict(row.value or {})
    merged.update(value)
    row.value = merged
    row.updated_by_user_id = user_id
    row.updated_by_employee_id = employee_id
    await session.flush()


async def site_config(session: AsyncSession) -> dict[str, Any]:
    """Descriptive text for the site, defaults filled in."""
    config = site_defaults()
    config.update({k: v for k, v in (await get_group(session, KEY_SITE)).items() if v != ""})
    return config


async def smtp_config(session: AsyncSession) -> dict[str, Any]:
    """The mail settings to actually send with. Includes the password — server-side only."""
    config = _smtp_defaults()
    stored = await get_group(session, KEY_SMTP)
    for field, value in stored.items():
        # An empty string in the row means "not set here", so the environment still wins.
        # False and 0 are real values and must survive.
        if value not in ("", None):
            config[field] = value
    return config


def smtp_config_public(config: dict[str, Any]) -> dict[str, Any]:
    """The same settings with the password replaced by whether there is one."""
    public = {k: v for k, v in config.items() if k != "password"}
    public["has_password"] = bool(config.get("password"))
    return public
