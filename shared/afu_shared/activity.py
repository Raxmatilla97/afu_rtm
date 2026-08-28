"""Recording what people do, for the admin panel's activity feed and usage figures.

One helper, used from the bot middleware and from the web endpoints, so both write rows the
panel can group together. The action keys are listed here rather than typed as free strings
at each call site: the panel groups by them, and a key that exists in two spellings is two
half-empty rows in every chart.

Recording must never break the thing being recorded. A failure here is logged and swallowed
— nobody's request should fail because the audit table was busy.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import ActivityEvent, Employee, User

logger = logging.getLogger(__name__)

SOURCE_BOT = "bot"
SOURCE_WEB = "web"

#: Every action key the panel knows how to label, with its Uzbek wording. A key missing
#: from here still records and still shows — it just shows as itself.
ACTION_LABELS: dict[str, str] = {
    "login.quick": "Tezkor kirish",
    "login.quick.setup": "Parol o'rnatdi (birinchi kirish)",
    "login.quick.reset": "Parolni tikladi",
    "login.hemis": "HEMIS orqali kirdi",
    "login.admin": "Admin panelga kirdi",
    "logout": "Hisobdan chiqdi",
    "bot.open": "Botni ochdi",
    "bot.menu": "Bot menyusi",
    "bot.button": "Botda tugma bosdi",
    "request.create": "Yangi murojaat yubordi",
    "request.assign": "Murojaatni tayinladi",
    "request.take": "Murojaatni o'z zimmasiga oldi",
    "request.start": "Ishni boshladi",
    "request.complete": "Murojaatni yakunladi",
    "request.return": "Murojaatni qaytarib yubordi",
    "request.status": "Holatni o'zgartirdi",
    "request.message": "Xabar yozdi",
    "request.rate": "Xizmatni baholadi",
    "inventory.movement": "Inventar harakati",
    "inventory.create": "Yangi inventar qo'shdi",
    "soft.upload": "Fayl yukladi",
    "soft.update": "Fayl ma'lumotini tahrirladi",
    "employee.roles": "Xodim rollarini o'zgartirdi",
    "hemis.sync": "HEMIS sinxronizatsiyasini ishga tushirdi",
    "settings.site": "Sayt sozlamalarini saqladi",
    "settings.smtp": "Pochta sozlamalarini saqladi",
    "settings.smtp.test": "Sinov xati yubordi",
    "group.on": "Guruhni uladi",
    "group.off": "Guruhni uzdi",
}


def action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action)


async def record(
    session: AsyncSession,
    *,
    action: str,
    source: str,
    employee: Employee | None = None,
    user: User | None = None,
    target: str | None = None,
    detail: str | None = None,
) -> None:
    """Append one event. Never raises.

    The actor's name is copied in rather than looked up later, so the feed still reads
    correctly after somebody leaves the university and their row is revoked.
    """
    try:
        actor_name: str | None = None
        if employee is not None:
            actor_name = employee.full_name
        elif user is not None:
            actor_name = user.email

        session.add(
            ActivityEvent(
                action=action[:48],
                source=source,
                employee_id=employee.id if employee is not None else None,
                user_id=user.id if user is not None else None,
                actor_name=actor_name[:200] if actor_name else None,
                target=target[:200] if target else None,
                detail=detail,
            )
        )
        await session.flush()
    except Exception as exc:  # noqa: BLE001 - an audit row must never break the action
        logger.warning("Could not record activity %r: %r", action, exc)


def describe(event: ActivityEvent) -> dict[str, Any]:
    """One feed row, ready for the panel."""
    return {
        "id": event.id,
        "created_at": event.created_at,
        "source": event.source,
        "action": event.action,
        "action_label": action_label(event.action),
        "actor_name": event.actor_name or "—",
        "employee_id": event.employee_id,
        "target": event.target,
        "detail": event.detail,
    }


async def record_for(
    session: AsyncSession,
    caller: Employee | User | None,
    *,
    action: str,
    source: str = SOURCE_WEB,
    target: str | None = None,
    detail: str | None = None,
) -> None:
    """``record`` for the web endpoints, which hold one ``caller`` of either kind."""
    await record(
        session,
        action=action,
        source=source,
        employee=caller if isinstance(caller, Employee) else None,
        user=caller if isinstance(caller, User) else None,
        target=target,
        detail=detail,
    )
