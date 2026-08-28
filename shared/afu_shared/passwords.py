"""Passwords for the quick login, shared by the bot, the backend and the worker.

Lives in ``shared`` because all three touch the same secret from different directions: the
bot checks a password typed into a chat, the backend checks one typed into the web form and
issues the reset token, and the worker mails that token out. A second copy of the hashing
rules in any of them would eventually disagree with the others, and the symptom would be a
password that works in one place and not the other.

The quick login exists because HEMIS moved its own sign-in behind One-ID, which most staff
have not linked yet. It trades a federated identity for a local one, so what it stores has
to be worth trusting on its own: a real hash (bcrypt, per-password salt), a policy that
rejects the passwords people reach for first, and a reset path that goes through an address
the person proved they own.
"""

import hashlib
import re
import secrets

import bcrypt

#: bcrypt silently ignores everything past 72 bytes, so a longer password would quietly
#: become its own prefix — two different passwords that both "work". Refused instead.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 6

#: Not a dictionary — just the handful that people actually type when a bot asks them to
#: invent a password on the spot.
_TRIVIAL = {
    "123456", "1234567", "12345678", "123456789", "1234567890",
    "password", "parol", "qwerty", "qwerty123", "111111", "000000",
    "admin", "admin123", "rtm123", "hemis", "afu2024", "afu2025",
}

_HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_HAS_DIGIT = re.compile(r"\d")


class WeakPassword(ValueError):
    """Raised with a message written for the person who typed it, in Uzbek."""


def validate_password(password: str, *, employee_id_number: str | None = None) -> str:
    """Return the password, or raise ``WeakPassword`` explaining what is wrong.

    Deliberately mild. The brief was "not hard, but not trivial either": long enough to be
    worth hashing, mixed enough that it is not a date of birth, and never the one string
    every attacker already has — the employee id number the user just typed on the screen
    before.
    """
    password = password.strip()

    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(
            f"Parol kamida {MIN_PASSWORD_LENGTH} ta belgidan iborat bo'lishi kerak."
        )
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise WeakPassword("Parol juda uzun — 72 belgidan oshmasin.")
    if " " in password:
        raise WeakPassword("Parolda bo'sh joy bo'lmasin.")
    if not _HAS_LETTER.search(password) or not _HAS_DIGIT.search(password):
        raise WeakPassword("Parolda kamida bitta harf va bitta raqam bo'lishi kerak.")
    if password.lower() in _TRIVIAL:
        raise WeakPassword("Bu parol juda oddiy — boshqasini o'ylab toping.")
    if employee_id_number and password.strip() == employee_id_number.strip():
        raise WeakPassword("Parol xodim ID raqamingizdan farq qilishi kerak.")

    return password


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish time check that tolerates a missing or corrupt stored hash.

    Returns False rather than raising when there is no hash yet: "this account has no
    password" and "that password is wrong" are the same answer to anyone guessing, and the
    callers have their own path for the first case.
    """
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def new_reset_token() -> tuple[str, str]:
    """A reset token and the hash to store: ``(token_for_the_email, hash_for_the_row)``.

    Only the hash is written to the database. A reset link sits in an inbox for days, and
    a database dump should not be a folder of working ones.
    """
    token = secrets.token_urlsafe(32)
    return token, hash_reset_token(token)


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def mask_email(email: str | None) -> str:
    """``sherzod.abdiyev@afu.uz`` → ``sh•••••@afu.uz``.

    Shown when a reset is requested, so the person can tell whether the address on file is
    still one they can open — without the screen handing a full address to whoever typed
    somebody else's id number.
    """
    if not email or "@" not in email:
        return "—"
    local, _, domain = email.partition("@")
    head = local[:2] if len(local) > 2 else local[:1]
    return f"{head}{'•' * 5}@{domain}"
