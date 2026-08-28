"""Quick login: an employee id number plus a password the employee sets here.

One module for both front doors. The bot asks these questions in a chat and the web asks
them in a form, but the rules — who may claim a row, when a wrong password locks the
account, what a reset does — have to be the same in both, or the answer to "why did it let
me in there and not here?" is nobody knows.

Why it exists at all: HEMIS now signs people in through One-ID, which most staff have not
linked and cannot remember a password for, so the OAuth route locks out the people it was
built to admit. The roster is already in this database, so an employee identifies
themselves with the id number on their card and a password they choose once.

What that costs, stated plainly: an id number is not a secret, so the *first* person to
type an unclaimed one owns that account. The mitigations here are that claiming sets a
password immediately (the window closes the moment the real employee logs in), that a
claim can never take a row away from a Telegram account HEMIS already verified, and that
``password_set_at`` records when it happened so an administrator can see it.
"""

import logging
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Employee
from afu_shared.passwords import (
    WeakPassword,
    hash_password,
    hash_reset_token,
    new_reset_token,
    validate_password,
    verify_password,
)
from afu_shared.settings import settings

logger = logging.getLogger(__name__)

__all__ = [
    "Outcome",
    "QuickLoginResult",
    "WeakPassword",
    "employee_by_id_number",
    "lock_minutes_remaining",
    "check_password",
    "claim_account",
    "set_recovery_email",
    "start_password_reset",
    "complete_password_reset",
    "link_telegram",
    "unlink_telegram",
    "LOCKOUT_THRESHOLD",
    "LOCKOUT_MINUTES",
]

#: Wrong passwords in a row before the account stops answering. Five is enough for a bad
#: memory and far too few to walk a list of id numbers with a guesser.
LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15


class Outcome(StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    #: Left the university, blocked, or HEMIS says inactive.
    NOT_ELIGIBLE = "not_eligible"
    #: Recognised, but nobody has set a password on this row yet.
    NEEDS_SETUP = "needs_setup"
    WRONG_PASSWORD = "wrong_password"
    LOCKED = "locked"


class QuickLoginResult:
    """The outcome plus whatever the caller needs to say something useful about it."""

    def __init__(
        self,
        outcome: Outcome,
        employee: Employee | None = None,
        *,
        locked_minutes: int = 0,
        attempts_left: int = 0,
    ) -> None:
        self.outcome = outcome
        self.employee = employee
        self.locked_minutes = locked_minutes
        self.attempts_left = attempts_left

    @property
    def ok(self) -> bool:
        return self.outcome is Outcome.OK


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def employee_by_id_number(session: AsyncSession, value: str | None) -> Employee | None:
    """Find one employee by id number, tolerating zero-padding — or nobody.

    Never picks between candidates. Systems disagree about leading zeros, so the second
    lookup strips them from both sides; if that makes two different employees look alike,
    the honest answer is "no match" rather than a coin flip. Handing somebody a colleague's
    account is the exact failure this whole login is being rebuilt to stop.
    """
    value = (value or "").strip()
    if not value:
        return None

    exact = (
        await session.execute(select(Employee).where(Employee.employee_id_number == value))
    ).scalars().all()
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        logger.error("Employee id number %r is not unique — refusing to choose", value)
        return None

    stripped = value.lstrip("0")
    if not stripped:
        return None
    rows = (
        await session.execute(
            select(Employee)
            .where(func.ltrim(Employee.employee_id_number, "0") == stripped)
            .limit(2)
        )
    ).scalars().all()
    if len(rows) == 1:
        return rows[0]
    if len(rows) > 1:
        logger.warning("Id number %r is ambiguous once zero-padding is ignored", value)
    return None


def lock_minutes_remaining(employee: Employee) -> int:
    """Minutes left on the lock, or 0. Public because both front doors report it."""
    until = employee.login_locked_until
    if until is None:
        return 0
    remaining = (until - _now()).total_seconds()
    return max(0, int(remaining // 60) + 1) if remaining > 0 else 0


async def check_password(
    session: AsyncSession, id_number: str, password: str
) -> QuickLoginResult:
    """The whole password check, counters included.

    Eligibility is judged before the password so a departed employee is told the truth
    instead of being left guessing at their own spelling.
    """
    employee = await employee_by_id_number(session, id_number)
    if employee is None:
        return QuickLoginResult(Outcome.NOT_FOUND)
    if not employee.is_eligible:
        return QuickLoginResult(Outcome.NOT_ELIGIBLE, employee)

    locked = lock_minutes_remaining(employee)
    if locked:
        return QuickLoginResult(Outcome.LOCKED, employee, locked_minutes=locked)

    if not employee.quick_password_hash:
        return QuickLoginResult(Outcome.NEEDS_SETUP, employee)

    if not verify_password(password, employee.quick_password_hash):
        employee.failed_login_count = (employee.failed_login_count or 0) + 1
        if employee.failed_login_count >= LOCKOUT_THRESHOLD:
            employee.login_locked_until = _now() + timedelta(minutes=LOCKOUT_MINUTES)
            employee.failed_login_count = 0
            await session.flush()
            logger.warning("Quick login locked for employee %s after repeated failures", employee.id)
            return QuickLoginResult(
                Outcome.LOCKED, employee, locked_minutes=LOCKOUT_MINUTES
            )
        await session.flush()
        return QuickLoginResult(
            Outcome.WRONG_PASSWORD,
            employee,
            attempts_left=LOCKOUT_THRESHOLD - employee.failed_login_count,
        )

    employee.failed_login_count = 0
    employee.login_locked_until = None
    # A successful login means the person can get in the ordinary way, so any reset link
    # sitting in their inbox stops working here rather than staying live for an hour.
    employee.password_reset_token_hash = None
    employee.password_reset_expires_at = None
    await session.flush()
    return QuickLoginResult(Outcome.OK, employee)


async def claim_account(
    session: AsyncSession,
    employee: Employee,
    password: str,
    *,
    telegram_user_id: int | None = None,
) -> None:
    """Set the first password on an unclaimed row.

    Refuses a row that already has a password (that is a reset, not a claim) and one that
    is already linked to a different Telegram account — that link came from a HEMIS login,
    which is stronger evidence than typing a number off a staff list.

    Raises ``WeakPassword`` or ``PermissionError`` with a message written for the user.
    """
    if employee.quick_password_hash:
        raise PermissionError("Bu hisobda parol allaqachon o'rnatilgan.")
    if (
        telegram_user_id is not None
        and employee.telegram_user_id is not None
        and employee.telegram_user_id != telegram_user_id
    ):
        raise PermissionError(
            "Bu xodim boshqa Telegram hisobiga bog'langan. RTM bilan bog'laning."
        )

    validate_password(password, employee_id_number=employee.employee_id_number)
    employee.quick_password_hash = hash_password(password)
    employee.password_set_at = _now()
    employee.failed_login_count = 0
    employee.login_locked_until = None
    await session.flush()
    logger.info("Quick login: employee %s claimed and set a password", employee.id)


async def set_recovery_email(session: AsyncSession, employee: Employee, email: str) -> None:
    employee.recovery_email = email.strip().lower()
    await session.flush()


async def start_password_reset(session: AsyncSession, employee: Employee) -> str | None:
    """Mint a reset token. Returns the token to mail, or None with no address on file."""
    if not employee.recovery_email:
        return None
    token, token_hash = new_reset_token()
    employee.password_reset_token_hash = token_hash
    employee.password_reset_sent_at = _now()
    employee.password_reset_expires_at = _now() + timedelta(
        minutes=settings.password_reset_ttl_minutes
    )
    await session.flush()
    return token


async def complete_password_reset(
    session: AsyncSession, token: str, password: str
) -> Employee | None:
    """Set a new password from a mailed token. Returns the employee, or None if unusable.

    The token is single-use: it is cleared here, so the link in the inbox stops working the
    moment it has done its job.
    """
    token_hash = hash_reset_token(token)
    employee = (
        await session.execute(
            select(Employee).where(Employee.password_reset_token_hash == token_hash)
        )
    ).scalar_one_or_none()
    if employee is None:
        return None
    if employee.password_reset_expires_at is None or employee.password_reset_expires_at < _now():
        return None

    validate_password(password, employee_id_number=employee.employee_id_number)
    employee.quick_password_hash = hash_password(password)
    employee.password_set_at = _now()
    employee.password_reset_token_hash = None
    employee.password_reset_expires_at = None
    employee.failed_login_count = 0
    employee.login_locked_until = None
    await session.flush()
    logger.info("Quick login: employee %s reset their password", employee.id)
    return employee


async def link_telegram(
    session: AsyncSession, employee: Employee, telegram_user_id: int
) -> None:
    """Point this Telegram account at this employee, and nowhere else.

    Only ever called after a password check or a fresh claim, so moving a link is a person
    proving who they are — from a new phone, a new Telegram account, or off a row the old
    HEMIS matcher had mis-assigned to them. Any other row holding this Telegram id is
    released, which is what makes that mis-assignment self-healing.
    """
    others = (
        await session.execute(
            select(Employee).where(
                Employee.telegram_user_id == telegram_user_id, Employee.id != employee.id
            )
        )
    ).scalars().all()
    for other in others:
        logger.info(
            "Quick login: moving Telegram %s from employee %s to %s",
            telegram_user_id, other.id, employee.id,
        )
        other.telegram_user_id = None
    # Flushed before the new link is written: employees.telegram_user_id is unique, and
    # assigning it while the old row still holds the value violates that constraint.
    await session.flush()

    employee.telegram_user_id = telegram_user_id
    await session.flush()


async def unlink_telegram(session: AsyncSession, employee: Employee) -> None:
    """/chiqish — forget which Telegram account this employee uses.

    The password stays: logging out is not forgetting who you are, and asking somebody to
    invent a new password every time they switch phones is how they end up writing it on
    the back of the id card.
    """
    employee.telegram_user_id = None
    await session.flush()
