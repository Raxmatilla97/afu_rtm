"""Session cookie minting.

Lives outside ``api/auth.py`` because three modules now issue sessions: admin login,
the OAuth callback, and (historically) the Telegram link poll.
"""

from fastapi import Response

from afu_shared.settings import settings
from app.security import create_access_token


def set_session_cookie(response: Response, *, subject: str, scope: str) -> None:
    token = create_access_token(
        subject=subject, scope=scope, expires_days=settings.session_ttl_days
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        # "lax" is required, not merely acceptable: the OAuth callback is a top-level GET
        # navigation from hemis.alfraganusuniversity.uz, and "strict" would withhold the
        # cookie on exactly that hop.
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
        max_age=settings.session_ttl_days * 24 * 3600,
    )


def clear_session_cookie(response: Response) -> None:
    # path must mirror set_session_cookie, or the browser keeps the original cookie.
    response.delete_cookie(settings.session_cookie_name, path="/")
