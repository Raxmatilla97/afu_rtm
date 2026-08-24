"""HEMIS OAuth2 login endpoints.

Mounted at the ROOT (``/oauth/*``), not under ``/api`` — the redirect URI registered with
HEMIS is ``https://rtm.afu.uz/oauth/callback``. The reverse proxy routes ``/oauth/*`` to
this service ahead of the SPA catch-all.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import OAuthAttemptStatus, OAuthFlow
from afu_shared.models import Employee, OAuthLoginAttempt
from afu_shared.settings import settings
from app.arq_pool import get_arq_pool
from app.deps import get_db
from app.services.employee_matcher import match_employee
from app.services.hemis_oauth import HemisOAuthError, build_authorize_url, exchange_code, fetch_userinfo
from app.session import set_session_cookie

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _terminal_page(title: str, message: str, *, ok: bool) -> HTMLResponse:
    """Self-contained end-of-flow page.

    Served by the backend rather than the SPA so the bot login never depends on the
    frontend build, and so an error can never surface as a raw stack trace.
    """
    icon = "✅" if ok else "⚠️"
    # Only success auto-closes. An error page that closes itself is unreadable, which is
    # exactly when the user most needs to see what went wrong.
    button = "" if ok else '<button onclick="closeApp()">Yopish</button>'
    auto_close = "setTimeout(closeApp, 1200);" if ok else ""
    haptic = "'success'" if ok else "'error'"

    return HTMLResponse(
        f"""<!doctype html>
<html lang="uz">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
         background:#0f172a; color:#e2e8f0; padding:24px; text-align:center; }}
  .card {{ max-width:420px; }}
  .icon {{ font-size:56px; line-height:1; }}
  h1 {{ font-size:20px; margin:16px 0 8px; }}
  p {{ font-size:15px; line-height:1.5; color:#94a3b8; margin:0; }}
  button {{ margin-top:24px; padding:12px 28px; font-size:15px; border:0; border-radius:10px;
            background:#334155; color:#e2e8f0; cursor:pointer; }}
</style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h1>{title}</h1>
    <p>{message}</p>
    {button}
  </div>
<script>
  var tg = window.Telegram && window.Telegram.WebApp;
  function closeApp() {{
    if (tg) {{ tg.close(); }} else {{ window.close(); }}
  }}
  if (tg) {{
    tg.ready();
    tg.expand();
    if (tg.HapticFeedback && tg.HapticFeedback.notificationOccurred) {{
      tg.HapticFeedback.notificationOccurred({haptic});
    }}
  }}
  {auto_close}
</script>
</body>
</html>""",
        status_code=200,
    )


def _safe_next_path(value: str | None) -> str | None:
    """Reject anything that could redirect off-site."""
    if not value:
        return None
    if not value.startswith("/") or value.startswith("//") or "://" in value:
        return None
    return value


async def _fail(
    session: AsyncSession,
    attempt: OAuthLoginAttempt,
    attempt_status: OAuthAttemptStatus,
    *,
    detail: str | None = None,
    title: str,
    message: str,
) -> Response:
    """Record why the attempt failed, commit it, and render a friendly page.

    The commit matters: the attempt row is the only durable record of what HEMIS returned,
    and it must survive even though the request ends in an error.
    """
    attempt.status = attempt_status.value
    attempt.completed_at = _now()
    if detail:
        attempt.error_detail = detail[:4000]
    await session.commit()
    return _terminal_page(title, message, ok=False)


def _user_type_token(userinfo: dict[str, Any]) -> str | None:
    """Normalize userinfo['type'], which may be a string, an int code, or a nested dict."""
    raw = userinfo.get("type")
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("code") or raw.get("name")
    if raw is None:
        return None
    text = str(raw).strip().lower()
    return text or None


@router.get("/login")
async def oauth_login(
    flow: str = Query(default=OAuthFlow.WEB.value),
    s: str | None = Query(default=None, description="Pre-created state (bot flow)"),
    next: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if s:
        # Bot flow: the bot already created the row, binding this login to a Telegram user.
        attempt = await session.get(OAuthLoginAttempt, s)
        if (
            attempt is None
            or attempt.flow != OAuthFlow.BOT.value
            or attempt.telegram_user_id is None
        ):
            logger.warning("Bot OAuth login with unusable state=%r", s)
            return _terminal_page(
                "Havola yaroqsiz",
                "Botga qaytib /start ni bosing va qaytadan urinib ko'ring.",
                ok=False,
            )

        if attempt.status != OAuthAttemptStatus.PENDING.value or attempt.expires_at < _now():
            # The button lives on the bot's anchor message, which sits in the chat for days,
            # and its state is minted when that screen is RENDERED — not when the button is
            # finally tapped. So a stale state here is the normal case, not an attack.
            # What actually matters is the Telegram binding, so carry it into a fresh state
            # instead of dead-ending the user. (Replay protection lives on the callback,
            # which still refuses to redeem a non-pending state.)
            attempt = OAuthLoginAttempt(
                state=secrets.token_urlsafe(32),
                flow=OAuthFlow.BOT.value,
                telegram_user_id=attempt.telegram_user_id,
                telegram_chat_id=attempt.telegram_chat_id,
                status=OAuthAttemptStatus.PENDING.value,
                expires_at=_now() + timedelta(seconds=settings.oauth_state_ttl_seconds),
            )
            session.add(attempt)
            await session.flush()

        state = attempt.state
    else:
        state = secrets.token_urlsafe(32)
        session.add(
            OAuthLoginAttempt(
                state=state,
                flow=OAuthFlow.WEB.value,
                next_path=_safe_next_path(next),
                status=OAuthAttemptStatus.PENDING.value,
                expires_at=_now() + timedelta(seconds=settings.oauth_state_ttl_seconds),
            )
        )
        await session.flush()

    return RedirectResponse(build_authorize_url(state=state), status_code=302)


@router.get("/callback")
async def oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> Response:
    attempt = await session.get(OAuthLoginAttempt, state) if state else None
    if attempt is None:
        logger.warning("HEMIS OAuth callback with unknown state=%r", state)
        return _terminal_page(
            "Havola yaroqsiz",
            "Kirish so'rovi topilmadi. Iltimos, qaytadan urinib ko'ring.",
            ok=False,
        )

    is_bot = attempt.flow == OAuthFlow.BOT.value

    def web_error(reason: str) -> Response:
        return RedirectResponse(f"/login?oauth_error={reason}", status_code=302)

    if error:
        resp = await _fail(
            session, attempt, OAuthAttemptStatus.DENIED,
            detail=f"{error}: {error_description or ''}".strip(),
            title="Kirish bekor qilindi", message="HEMIS orqali kirishga ruxsat berilmadi.",
        )
        return resp if is_bot else web_error("denied")

    # A non-pending row means this code was already redeemed — refuse to mint a second session.
    if attempt.status != OAuthAttemptStatus.PENDING.value or attempt.expires_at < _now():
        resp = await _fail(
            session, attempt, OAuthAttemptStatus.STATE_EXPIRED,
            detail=f"status={attempt.status} expires_at={attempt.expires_at}",
            title="Havola muddati tugagan", message="Iltimos, kirishni qaytadan boshlang.",
        )
        return resp if is_bot else web_error("expired")

    if not code:
        resp = await _fail(
            session, attempt, OAuthAttemptStatus.TOKEN_ERROR, detail="no code in callback",
            title="Xatolik", message="HEMIS kod qaytarmadi. Qaytadan urinib ko'ring.",
        )
        return resp if is_bot else web_error("no_code")

    try:
        token_payload = await exchange_code(code)
    except HemisOAuthError as exc:
        resp = await _fail(
            session, attempt, OAuthAttemptStatus.TOKEN_ERROR, detail=exc.detail,
            title="Xatolik", message="HEMIS bilan bog'lanishda xatolik yuz berdi.",
        )
        return resp if is_bot else web_error("token_error")

    access_token = token_payload.get("access_token") or token_payload.get("accessToken")
    try:
        userinfo = await fetch_userinfo(str(access_token))
    except HemisOAuthError as exc:
        resp = await _fail(
            session, attempt, OAuthAttemptStatus.USERINFO_ERROR, detail=exc.detail,
            title="Xatolik", message="HEMIS'dan ma'lumotlaringizni olib bo'lmadi.",
        )
        return resp if is_bot else web_error("userinfo_error")

    # Persist the payload before any decision — this is what makes a failed match diagnosable.
    attempt.userinfo_json = userinfo

    user_type = _user_type_token(userinfo)
    allowed = {t.strip().lower() for t in settings.oauth_allowed_user_types.split(",") if t.strip()}
    if user_type is not None and user_type not in allowed:
        # Fail closed only on a value we positively recognize as non-staff. An unfamiliar
        # representation is logged and allowed through, because a strict gate on an
        # unexpected shape would lock out every employee with no obvious cause.
        if "student" in user_type:
            resp = await _fail(
                session, attempt, OAuthAttemptStatus.WRONG_TYPE, detail=f"type={user_type!r}",
                title="Ruxsat yo'q",
                message="Bu tizim faqat universitet xodimlari uchun.",
            )
            return resp if is_bot else web_error("wrong_type")
        logger.warning(
            "HEMIS OAuth: unrecognized user type %r (allowed=%s) — allowing through", user_type, allowed
        )

    match = await match_employee(session, userinfo)
    if match is None:
        resp = await _fail(
            session, attempt, OAuthAttemptStatus.UNMATCHED,
            title="Xodim topilmadi",
            message=(
                "Sizni HEMIS ma'lumotlaringiz bo'yicha xodimlar ro'yxatidan topa olmadik. "
                "Iltimos, RTM bilan bog'laning."
            ),
        )
        return resp if is_bot else web_error("unmatched")

    employee = match.employee
    if not employee.is_eligible:
        resp = await _fail(
            session, attempt, OAuthAttemptStatus.INELIGIBLE,
            detail=f"employee_id={employee.id} status={employee.employee_status_code}",
            title="Ruxsat cheklangan",
            message="Sizning hisobingiz faol emas. Iltimos, RTM bilan bog'laning.",
        )
        return resp if is_bot else web_error("ineligible")

    oauth_subject = str(userinfo.get("id") or "").strip()
    if oauth_subject and employee.hemis_oauth_subject not in (None, oauth_subject):
        resp = await _fail(
            session, attempt, OAuthAttemptStatus.UNMATCHED, detail="subject_conflict",
            title="Xatolik", message="Hisobingizda nomuvofiqlik aniqlandi. RTM bilan bog'laning.",
        )
        return resp if is_bot else web_error("subject_conflict")

    if oauth_subject:
        employee.hemis_oauth_subject = oauth_subject
    employee.hemis_uuid = str(userinfo.get("uuid") or "") or employee.hemis_uuid
    employee.hemis_login = str(userinfo.get("login") or "") or employee.hemis_login
    employee.hemis_email = str(userinfo.get("email") or "") or employee.hemis_email
    employee.hemis_phone = str(userinfo.get("phone") or "") or employee.hemis_phone
    employee.hemis_university_id = (
        str(userinfo.get("university_id") or "") or employee.hemis_university_id
    )
    employee.oauth_verified_at = _now()

    attempt.status = OAuthAttemptStatus.MATCHED.value
    attempt.match_strategy = match.strategy
    attempt.matched_employee_id = employee.id
    attempt.completed_at = _now()

    logger.info(
        "HEMIS OAuth login matched employee_id=%s via %r (flow=%s)",
        employee.id, match.strategy, attempt.flow,
    )

    if is_bot:
        return await _finish_bot_flow(session, attempt, employee)

    response = RedirectResponse(attempt.next_path or "/", status_code=302)
    set_session_cookie(response, subject=str(employee.id), scope="employee")
    return response


async def _finish_bot_flow(
    session: AsyncSession, attempt: OAuthLoginAttempt, employee: Employee
) -> Response:
    """Link the Telegram account, then hand off to the worker to DM the user.

    ``verified_at`` is deliberately NOT set here — it stays gated on the contact share, which
    is what proves the phone number belongs to this Telegram account.
    """
    tg_user_id = attempt.telegram_user_id
    if tg_user_id is None:
        return await _fail(
            session, attempt, OAuthAttemptStatus.UNMATCHED, detail="bot flow without telegram_user_id",
            title="Xatolik", message="Telegram hisobi aniqlanmadi. Botda qaytadan urinib ko'ring.",
        )

    if employee.telegram_user_id is not None and employee.telegram_user_id != tg_user_id:
        return await _fail(
            session, attempt, OAuthAttemptStatus.UNMATCHED, detail="employee already linked",
            title="Allaqachon bog'langan",
            message="Bu xodim boshqa Telegram hisobiga bog'langan. RTM bilan bog'laning.",
        )

    other = await _employee_by_telegram(session, tg_user_id)
    if other is not None and other.id != employee.id:
        return await _fail(
            session, attempt, OAuthAttemptStatus.UNMATCHED, detail="telegram already linked",
            title="Allaqachon bog'langan",
            message="Telegram hisobingiz boshqa xodimga bog'langan. RTM bilan bog'laning.",
        )

    employee.telegram_user_id = tg_user_id
    await session.commit()

    # The bot is long-polling and has no HTTP surface, so it cannot be called directly.
    # The worker owns the Bot client and delivers the follow-up message.
    pool = await get_arq_pool()
    await pool.enqueue_job("notify_oauth_login_complete", employee.id, tg_user_id)

    return _terminal_page(
        "Tasdiqlandi",
        f"Xush kelibsiz, {employee.full_name}! Botga qayting.",
        ok=True,
    )


async def _employee_by_telegram(session: AsyncSession, telegram_user_id: int) -> Employee | None:
    return (
        await session.execute(
            select(Employee).where(Employee.telegram_user_id == telegram_user_id)
        )
    ).scalar_one_or_none()
