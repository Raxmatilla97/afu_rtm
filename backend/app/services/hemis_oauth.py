"""HEMIS OAuth2 authorization-code client.

HEMIS runs a Yii2 OAuth2 server whose exact response conventions we have not been able to
observe yet (the redirect URI is registered against the production domain, so the flow
cannot be exercised anywhere else). Everything here is therefore written to tolerate more
than one plausible shape and to log loudly which one actually worked, so the first real
login on rtm.afu.uz settles the question.
"""

import logging
from typing import Any
from urllib.parse import parse_qs, urlencode

import httpx

from afu_shared.settings import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(20.0)
#: Upstream bodies are stored on the attempt row for diagnosis; cap them so a stray HTML
#: error page cannot bloat the table.
_MAX_ERROR_BODY = 2000


class HemisOAuthError(Exception):
    """Raised when the upstream exchange fails. ``stage`` is 'token' or 'userinfo'."""

    def __init__(self, stage: str, detail: str) -> None:
        super().__init__(f"{stage}: {detail}")
        self.stage = stage
        self.detail = detail


def build_authorize_url(*, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.employee_client_id,
        # Sent verbatim from settings, never reconstructed from the incoming request —
        # OAuth servers compare this byte-for-byte against what was registered.
        "redirect_uri": settings.employee_redirect_uri,
        "state": state,
    }
    # Yii2 providers commonly reject a scope they do not know, so only send one if configured.
    if settings.employee_oauth_scope:
        params["scope"] = settings.employee_oauth_scope

    separator = "&" if "?" in settings.employee_url_authorize else "?"
    return f"{settings.employee_url_authorize}{separator}{urlencode(params)}"


def _parse_token_body(resp: httpx.Response) -> dict[str, Any]:
    """Parse a token response that may be JSON or form-encoded."""
    try:
        parsed = resp.json()
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    try:
        flat = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(resp.text).items()}
        if flat:
            return flat
    except Exception:
        pass

    return {}


def _truncate(text: str) -> str:
    return text[:_MAX_ERROR_BODY]


async def exchange_code(code: str) -> dict[str, Any]:
    """Trade an authorization code for an access token."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.employee_client_id,
        "client_secret": settings.employee_client_secret,
        "redirect_uri": settings.employee_redirect_uri,
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
        try:
            resp = await client.post(
                settings.employee_url_access_token,
                data=data,  # form-encoded first: the Yii2 oauth2-server convention
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise HemisOAuthError("token", f"request failed: {exc!r}") from exc

    # Parse before checking the status: OAuth error bodies ({"error": "invalid_client"})
    # are far more useful than the status code alone.
    payload = _parse_token_body(resp)
    logger.info(
        "HEMIS token response: status=%s content_type=%s keys=%s",
        resp.status_code,
        resp.headers.get("content-type"),
        sorted(payload.keys()),  # key names only — never log the token value itself
    )

    token = payload.get("access_token") or payload.get("accessToken")
    if not token:
        raise HemisOAuthError(
            "token",
            f"no access_token in response (status={resp.status_code}, "
            f"content_type={resp.headers.get('content-type')}): {_truncate(resp.text)}",
        )

    return payload


def _normalize_userinfo(raw: Any) -> dict[str, Any] | None:
    """Unwrap a possible envelope, e.g. {"success": true, "data": {...}}."""
    if not isinstance(raw, dict):
        return None
    for key in ("data", "result", "user"):
        inner = raw.get(key)
        if isinstance(inner, dict) and (inner.get("id") or inner.get("uuid")):
            return inner
    if raw.get("id") or raw.get("uuid"):
        return raw
    return None


async def fetch_userinfo(access_token: str) -> dict[str, Any]:
    """Fetch the resource owner's details.

    Tries three auth conventions in order; the one that works is logged so it can be
    made the default once observed in production.
    """
    base = httpx.URL(settings.employee_url_resource_owner_details)

    attempts: list[tuple[str, dict[str, str], httpx.URL]] = [
        ("bearer_header", {"Authorization": f"Bearer {access_token}"}, base),
        # Note the hyphen: HEMIS/Yii2 installs commonly use `access-token`, not `access_token`.
        ("access-token_query", {}, base.copy_merge_params({"access-token": access_token})),
        ("access_token_query", {}, base.copy_merge_params({"access_token": access_token})),
    ]

    failures: list[str] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
        for name, headers, url in attempts:
            try:
                resp = await client.get(url, headers={"Accept": "application/json", **headers})
            except httpx.HTTPError as exc:
                failures.append(f"{name}: request failed {exc!r}")
                continue

            if resp.status_code != 200:
                failures.append(f"{name}: status {resp.status_code}: {_truncate(resp.text)}")
                continue

            try:
                raw = resp.json()
            except Exception:
                failures.append(f"{name}: non-JSON body: {_truncate(resp.text)}")
                continue

            userinfo = _normalize_userinfo(raw)
            if userinfo is None:
                failures.append(f"{name}: unrecognized payload shape: {_truncate(resp.text)}")
                continue

            logger.info("HEMIS userinfo strategy %r succeeded", name)
            return userinfo

    raise HemisOAuthError("userinfo", " | ".join(failures))
