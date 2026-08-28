"""Outgoing email. One letter so far: the password reset link.

SMTP is blocking, so the send runs in a thread — an arq worker shares one event loop with
every notification job, and a mail server that takes eight seconds to answer would stall
Telegram delivery behind it.

With ``SMTP_HOST`` unset the job logs loudly and gives up rather than pretending. Silence
here would be the worst outcome available: somebody waits for a letter that was never sent
and never finds out why.
"""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from afu_shared.db import session_scope
from afu_shared.models import Employee
from afu_shared.settings import settings

logger = logging.getLogger(__name__)


def _build_message(*, to_address: str, full_name: str, link: str, ttl_minutes: int) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = "RTM Murojaatlar — parolni tiklash"
    message["From"] = settings.smtp_from
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


def _send_blocking(message: EmailMessage) -> None:
    if settings.smtp_starttls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
        return

    # Implicit TLS (usually port 465).
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


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

    if not to_address:
        logger.error("send_password_reset_email: employee %s has no recovery email", employee_id)
        return

    if not settings.smtp_host:
        logger.error(
            "SMTP_HOST is not configured — the reset link for employee %s could not be sent. "
            "Set SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD in .env.",
            employee_id,
        )
        return

    message = _build_message(
        to_address=to_address,
        full_name=full_name,
        link=f"{settings.public_base_url.rstrip('/')}/reset-password?token={token}",
        ttl_minutes=settings.password_reset_ttl_minutes,
    )

    try:
        await asyncio.to_thread(_send_blocking, message)
    except (smtplib.SMTPException, OSError) as exc:
        # Named rather than swallowed: "the letter never arrived" is otherwise indis-
        # tinguishable from a typo in the address, and the two have different fixes.
        logger.error("Could not send the reset email for employee %s: %r", employee_id, exc)
        return

    logger.info("Password reset email sent for employee %s", employee_id)
