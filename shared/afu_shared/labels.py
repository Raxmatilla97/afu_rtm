"""User-facing Uzbek labels shared by the bot, the worker and the API.

Kept in ``shared`` so the bot, the worker's notification DMs and (optionally) API responses
all render a request status the same way — previously each place had its own copy, and the
staff detail screen printed the raw enum value.
"""

from afu_shared.enums import InventoryStatus, MovementReason, RequestStatus

REQUEST_STATUS_LABELS: dict[str, str] = {
    RequestStatus.NEW.value: "🆕 Yangi",
    RequestStatus.ASSIGNED.value: "👤 Tayinlangan",
    RequestStatus.IN_PROGRESS.value: "⏳ Jarayonda",
    RequestStatus.WAITING.value: "⏸ Inventar kutilmoqda",
    RequestStatus.COMPLETED.value: "✅ Bajarilgan",
    RequestStatus.CANCELLED.value: "❌ Bekor qilingan",
    RequestStatus.RETURNED.value: "🚫 Qaytarib yuborilgan",
}


def status_label(value: str) -> str:
    """Uzbek label for a request status, falling back to the raw value if unknown."""
    return REQUEST_STATUS_LABELS.get(value, value)


#: Reply-keyboard button captions the worker needs when it DMs a contact request,
#: kept here so bot and worker cannot drift apart.
BTN_SHARE_CONTACT = "📱 Telefon raqamni ulashish"


MOVEMENT_REASON_LABELS: dict[str, str] = {
    MovementReason.PURCHASE.value: "🛒 Sotib olindi",
    MovementReason.CONSUMPTION.value: "🔧 Ishlatildi",
    MovementReason.ADJUSTMENT.value: "✏️ Tuzatish",
    MovementReason.WRITE_OFF.value: "🗑 Hisobdan chiqarildi",
    MovementReason.RETURN.value: "↩️ Qaytarildi",
}

INVENTORY_STATUS_LABELS: dict[str, str] = {
    InventoryStatus.AVAILABLE.value: "✅ Mavjud",
    InventoryStatus.PLANNED.value: "📝 Rejalashtirilgan",
    InventoryStatus.ORDERED.value: "🚚 Buyurtma qilingan",
    InventoryStatus.ARCHIVED.value: "📦 Arxivda",
}


def movement_reason_label(value: str) -> str:
    return MOVEMENT_REASON_LABELS.get(value, value)


def inventory_status_label(value: str) -> str:
    return INVENTORY_STATUS_LABELS.get(value, value)
