"""How a person is named and labelled everywhere a card is drawn.

Two rules live here, and both exist because a Telegram card is read at a glance in a chat
that is already full:

* **Names are shortened to familiya + ism.** Uzbek full names carry a patronymic
  ("Fayziyev Raxmatilla Baxtiyor o'g'li"), and printing it on every card costs a whole line
  per person while adding nothing anybody uses — the assignee list on a busy request was
  wrapping three times. The full name is still what the web shows and what HEMIS stores;
  this is a rendering choice, never a stored one.
* **Management requests are labelled by role.** A request filed by a Boshliq is not the
  same object as one filed by a lecturer: it arrives already assigned, with a deadline
  somebody has committed RTM to. The group has to be able to tell the two apart before
  reading a word of the body.
"""

from afu_shared.models import Employee

__all__ = [
    "ROLE_ADMIN",
    "ROLE_BOSHLIQ",
    "ROLE_LABELS",
    "role_label",
    "role_of",
    "short_name",
]

#: Stored on the request at filing time, never re-derived. Somebody's roles change; what
#: they were when they made the promise does not.
ROLE_ADMIN = "admin"
ROLE_BOSHLIQ = "boshliq"

ROLE_LABELS: dict[str, str] = {
    ROLE_ADMIN: "ADMIN",
    ROLE_BOSHLIQ: "BOSHLIQ",
}


def short_name(full_name: str | None, *, default: str = "—") -> str:
    """Familiya + ism, dropping the patronymic. "F.I" rather than "F.I.SH".

    A one- or two-word name is returned untouched: there is nothing to drop, and guessing
    would turn a mononym into an empty string.
    """
    if not full_name:
        return default
    parts = full_name.split()
    if not parts:
        return default
    return " ".join(parts[:2])


def role_of(employee: Employee | None) -> str | None:
    """Which management role a request filed by ``employee`` should carry, if any.

    Admin wins over Boshliq for somebody holding both — that is the more senior of the two
    and the one the group needs to see. An employee who is only an Admin gets ``None``:
    filing a directive is a Boshliq's job, and the role check that enforces it lives on
    ``Employee.can_file_managed_request``.
    """
    if employee is None or not employee.can_file_managed_request:
        return None
    return ROLE_ADMIN if employee.is_admin else ROLE_BOSHLIQ


def role_label(role: str | None) -> str | None:
    return ROLE_LABELS.get(role) if role else None
