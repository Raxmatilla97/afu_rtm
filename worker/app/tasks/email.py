"""Outgoing email: the password reset link, and the test letter that proves it works.

SMTP is blocking, so every send runs in a thread — an arq worker shares one event loop with
every notification job, and a mail server that takes eight seconds to answer would stall
Telegram delivery behind it.

Two lessons from the first real configuration are built in here. Institutional mail servers
usually refuse to send as any address other than the account that authenticated, so a
refused sender is retried once as the account itself rather than simply lost. And the
outcome of a test send is written back to the settings row: an administrator configuring
mail should not have to read container logs to find out that the password was wrong.
"""

import asyncio
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr

from afu_shared.db import session_scope
from afu_shared.models import KEY_SMTP, Employee
from afu_shared.settings import settings
from afu_shared.site_settings import resolve_from_address, save_group, smtp_config

logger = logging.getLogger(__name__)


def _build_message(
    *, to_address: str, full_name: str, link: str, ttl_minutes: int, from_address: str
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = "RTM Murojaatlar — parolni tiklash"
    message["From"] = from_address
    message["To"] = to_address

    text = (
        f"Assalomu alaykum, {full_name}!\n\n"
        "RTM Murojaatlar tizimida parolni tiklash so'raldi.\n\n"
        f"Yangi parol o'rnatish uchun quyidagi havolaga o'ting:\n{link}\n\n"
        f"Havola {ttl_minutes} daqiqa davomida amal qiladi va bir marta ishlatiladi.\n\n"
        "Agar parolni tiklashni siz so'ramagan bo'lsangiz, bu xatga e'tibor bermang — "
        "parolingiz o'zgarmaydi.\n\n"
        "RTM — Alfraganus University"
    )
    message.set_content(text)

    # A plain-text alternative is not a nicety here: some university mail clients strip
    # HTML entirely, and a reset letter that arrives blank is worse than none.
    message.add_alternative(
        f"""<html><body style="font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
color:#0f172a;line-height:1.6">
<p>Assalomu alaykum, <b>{full_name}</b>!</p>
<p>RTM Murojaatlar tizimida parolni tiklash so'raldi.</p>
<p style="margin:24px 0">
  <a href="{link}" style="background:#1d4ed8;color:#fff;text-decoration:none;
     padding:12px 22px;border-radius:8px;display:inline-block">Yangi parol o'rnatish</a>
</p>
<p style="color:#475569;font-size:14px">Yoki havolani brauzerga nusxalang:<br>
  <a href="{link}">{link}</a></p>
<p style="color:#475569;font-size:14px">Havola {ttl_minutes} daqiqa davomida amal qiladi
  va faqat bir marta ishlatiladi.</p>
<p style="color:#475569;font-size:14px">Agar parolni tiklashni siz so'ramagan bo'lsangiz,
  bu xatga e'tibor bermang — parolingiz o'zgarmaydi.</p>
<p style="color:#94a3b8;font-size:13px">RTM — Alfraganus University</p>
</body></html>""",
        subtype="html",
    )
    return message


def _send_blocking(message: EmailMessage, config: dict) -> None:
    """Deliver one message. ``config`` comes from the panel, falling back to the env vars."""
    host = config["host"]
    port = int(config.get("port") or 587)
    user = config.get("user") or ""
    password = config.get("password") or ""

    if config.get("starttls", True):
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.send_message(message)
        return

    # Implicit TLS (usually port 465).
    with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
        if user:
            smtp.login(user, password)
        smtp.send_message(message)


def explain(exc: Exception, config: dict) -> str:
    """One Uzbek sentence naming the fix, not the exception.

    These are the failures that actually happen when somebody fills the form in for the
    first time; anything unrecognised falls through with its own text, which is still more
    use than "xatolik".
    """
    user = config.get("user") or "—"

    if isinstance(exc, smtplib.SMTPSenderRefused):
        return (
            f"Server «{user}» hisobidan boshqa manzil nomidan xat yuborishga ruxsat "
            f"bermadi. «Jo'natuvchi manzil» maydoniga aynan {user} ni yozing "
            f"(masalan: RTM Murojaatlar <{user}>)."
        )
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "Login yoki parol noto'g'ri — server hisobni tanimadi."
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "Server qabul qiluvchi manzilni rad etdi. Manzilni tekshiring."
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return (
            "Server bu ulanish turini qo'llamaydi. STARTTLS belgisini o'zgartirib ko'ring "
            "(587-port uchun yoqilgan, 465-port uchun o'chirilgan bo'ladi)."
        )
    if isinstance(exc, (TimeoutError, ConnectionRefusedError, OSError)):
        return (
            "Serverga ulanib bo'lmadi. Manzil va portni tekshiring "
            "(587 — STARTTLS, 465 — SSL)."
        )
    return f"Xatolik: {exc}"


async def _deliver(message: EmailMessage, config: dict) -> tuple[bool, str | None]:
    """Send, retrying once as the authenticated account if the sender was refused.

    Returns ``(ok, error_message)``. The retry exists because the alternative is a
    password reset that silently never arrives: the reporter is waiting for a letter, and
    "the From address is not the login" is a configuration detail they cannot see or fix.
    """
    try:
        await asyncio.to_thread(_send_blocking, message, config)
        return True, None
    except smtplib.SMTPSenderRefused as exc:
        account = (config.get("user") or "").strip()
        _, current = parseaddr(message["From"] or "")
        if not account or current.lower() == account.lower():
            return False, explain(exc, config)

        logger.warning(
            "Sender %r refused; retrying as the authenticated account %r", current, account
        )
        del message["From"]
        message["From"] = account
        try:
            await asyncio.to_thread(_send_blocking, message, config)
        except (smtplib.SMTPException, OSError) as retry_exc:
            return False, explain(retry_exc, config)
        return True, (
            f"Xat yuborildi, lekin «{current}» nomidan emas — server faqat {account} "
            f"nomidan yuborishga ruxsat berdi. «Jo'natuvchi manzil» ni shunga moslang."
        )
    except (smtplib.SMTPException, OSError) as exc:
        return False, explain(exc, config)


async def _record_test_result(to_address: str, ok: bool, message: str | None) -> None:
    """Put the outcome where the person who pressed the button will see it."""
    async with session_scope() as session:
        await save_group(
            session,
            KEY_SMTP,
            {
                "last_test": {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "to": to_address,
                    "ok": ok,
                    "message": message,
                }
            },
        )


async def send_password_reset_email(ctx: dict, employee_id: int, token: str) -> None:
    """Mail one reset link.

    The token arrives as an argument rather than being read back from the row: only its
    hash is stored, so this is the last place it exists in readable form.
    """
    async with session_scope() as session:
        employee = await session.get(Employee, employee_id)
        if employee is None:
            logger.error("send_password_reset_email: employee %s not found", employee_id)
            return
        to_address = employee.recovery_email
        full_name = employee.full_name
        # Read inside the session: the panel may have changed the mail server since this
        # job was queued, and the newer settings are the ones worth trying.
        config = await smtp_config(session)

    if not to_address:
        logger.error("send_password_reset_email: employee %s has no recovery email", employee_id)
        return

    if not config.get("host"):
        logger.error(
            "No SMTP host configured — the reset link for employee %s could not be sent. "
            "Set it in the admin panel (Sozlamalar va kuzatuv) or as SMTP_HOST in .env.",
            employee_id,
        )
        return

    message = _build_message(
        to_address=to_address,
        full_name=full_name,
        link=f"{settings.public_base_url.rstrip('/')}/reset-password?token={token}",
        ttl_minutes=settings.password_reset_ttl_minutes,
        from_address=resolve_from_address(config) or settings.smtp_from,
    )

    ok, note = await _deliver(message, config)
    if not ok:
        # Named rather than swallowed: "the letter never arrived" is otherwise indis-
        # tinguishable from a typo in the address, and the two have different fixes.
        logger.error("Reset email for employee %s failed: %s", employee_id, note)
        return

    logger.info("Password reset email sent for employee %s%s", employee_id, f" ({note})" if note else "")


async def send_test_email(ctx: dict, to_address: str) -> None:
    """Prove the mail settings work, from the panel, before somebody needs them.

    Its own job rather than a synchronous send inside the request: SMTP can take half a
    minute to fail, and an admin watching a spinner cannot tell a slow server from a hung
    one. The result is written back to the settings row, so the answer appears on the page
    that asked the question.
    """
    async with session_scope() as session:
        config = await smtp_config(session)

    if not config.get("host"):
        await _record_test_result(to_address, False, "Pochta serveri (host) kiritilmagan.")
        return

    from_address = resolve_from_address(config)
    if not from_address:
        await _record_test_result(
            to_address,
            False,
            "Jo'natuvchi manzil ham, login ham bo'sh — kamida bittasini to'ldiring.",
        )
        return

    message = EmailMessage()
    message["Subject"] = "RTM Murojaatlar — sinov xati"
    message["From"] = from_address
    message["To"] = to_address
    message.set_content(
        "Bu — RTM Murojaatlar tizimidan yuborilgan sinov xati.\n\n"
        "Agar shu xatni olgan bo'lsangiz, pochta sozlamalari to'g'ri ishlayapti va "
        "parolni tiklash havolalari ham yetib boradi.\n\n"
        "RTM — Alfraganus University"
    )

    ok, note = await _deliver(message, config)
    if ok:
        logger.info("Test email sent to %s%s", to_address, f" ({note})" if note else "")
        await _record_test_result(to_address, True, note or "Xat muvaffaqiyatli yuborildi.")
        return

    logger.error("Test email to %s failed: %s", to_address, note)
    await _record_test_result(to_address, False, note)
