"""User-facing Uzbek labels shared by the bot, the worker and the API.

Kept in ``shared`` so the bot, the worker's notification DMs and (optionally) API responses
all render a request status the same way — previously each place had its own copy, and the
staff detail screen printed the raw enum value.
"""

from afu_shared.enums import RequestStatus

REQUEST_STATUS_LABELS: dict[str, str] = {
    RequestStatus.NEW.value: "🆕 Yangi",
    RequestStatus.ASSIGNED.value: "👤 Tayinlangan",
    RequestStatus.IN_PROGRESS.value: "⏳ Jarayonda",
    RequestStatus.COMPLETED.value: "✅ Bajarilgan",
    RequestStatus.CANCELLED.value: "❌ Bekor qilingan",
}


def status_label(value: str) -> str:
    """Uzbek label for a request status, falling back to the raw value if unknown."""
    return REQUEST_STATUS_LABELS.get(value, value)


#: Reply-keyboard button captions the worker needs when it DMs a contact request,
#: kept here so bot and worker cannot drift apart.
BTN_SHARE_CONTACT = "📱 Telefon raqamni ulashish"
