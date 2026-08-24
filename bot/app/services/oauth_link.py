"""Builds the per-user HEMIS login URL opened by the bot's WebApp button."""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import OAuthAttemptStatus, OAuthFlow
from afu_shared.models import OAuthLoginAttempt
from afu_shared.settings import settings


async def create_login_url(
    session: AsyncSession, *, telegram_user_id: int, chat_id: int
) -> str:
    """Reserve an OAuth state bound to this Telegram user and return the login URL.

    The bot writes the state row itself (it shares the database with the backend), so the
    identity of the person starting the login is fixed before HEMIS is ever contacted —
    the callback does not have to trust anything the webview sends back.
    """
    state = secrets.token_urlsafe(32)
    session.add(
        OAuthLoginAttempt(
            state=state,
            flow=OAuthFlow.BOT.value,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=chat_id,
            status=OAuthAttemptStatus.PENDING.value,
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=settings.oauth_state_ttl_seconds),
        )
    )
    # DbSessionMiddleware commits when the handler returns.
    await session.flush()

    return f"{settings.public_base_url}/oauth/login?flow=bot&s={state}"
