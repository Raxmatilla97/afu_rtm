"""The admin console: site settings, mail settings, and what people have been doing.

Everything here is admin-only except the one public endpoint at the bottom, which exists so
the browser tab can carry the site's own title instead of a hard-coded string.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared import activity, site_settings
from afu_shared.models import ActivityEvent, Employee, User
from app.arq_pool import get_arq_pool
from app.deps import get_admin_actor, get_db
from app.schemas.admin_console import (
    ActivityDay,
    ActivityEventResponse,
    ActorActivity,
    SiteConfig,
    SiteConfigPublic,
    SmtpConfigPublic,
    SmtpConfigUpdate,
    SmtpTestRequest,
)

router = APIRouter(tags=["admin"])


def _actor_ids(actor: User | Employee) -> tuple[int | None, int | None]:
    """(user_id, employee_id) — the panel admin has one, a HEMIS admin the other."""
    if isinstance(actor, User):
        return actor.id, None
    return None, actor.id


def _as_employee(actor: User | Employee) -> Employee | None:
    return actor if isinstance(actor, Employee) else None


def _as_user(actor: User | Employee) -> User | None:
    return actor if isinstance(actor, User) else None


# --------------------------------------------------------------------------- site settings


@router.get("/admin/settings/site", response_model=SiteConfig)
async def get_site_settings(
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> SiteConfig:
    return SiteConfig(**await site_settings.site_config(session))


@router.post("/admin/settings/site", response_model=SiteConfig)
async def save_site_settings(
    payload: SiteConfig,
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> SiteConfig:
    user_id, employee_id = _actor_ids(actor)
    await site_settings.save_group(
        session,
        site_settings.KEY_SITE,
        payload.model_dump(),
        user_id=user_id,
        employee_id=employee_id,
    )
    await activity.record(
        session,
        action="settings.site",
        source=activity.SOURCE_WEB,
        employee=_as_employee(actor),
        user=_as_user(actor),
        target=payload.title,
    )
    return SiteConfig(**await site_settings.site_config(session))


# --------------------------------------------------------------------------- mail settings


@router.get("/admin/settings/smtp", response_model=SmtpConfigPublic)
async def get_smtp_settings(
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> SmtpConfigPublic:
    config = await site_settings.smtp_config(session)
    return SmtpConfigPublic(**site_settings.smtp_config_public(config))


@router.post("/admin/settings/smtp", response_model=SmtpConfigPublic)
async def save_smtp_settings(
    payload: SmtpConfigUpdate,
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> SmtpConfigPublic:
    """Save the mail server.

    An empty password means "leave the stored one alone" rather than "erase it": the form
    never receives the current password, so posting the form back would otherwise wipe it
    every time somebody corrected a typo in the host name.
    """
    values: dict[str, Any] = payload.model_dump(exclude={"password"})
    if payload.password:
        values["password"] = payload.password

    user_id, employee_id = _actor_ids(actor)
    await site_settings.save_group(
        session, site_settings.KEY_SMTP, values, user_id=user_id, employee_id=employee_id
    )
    await activity.record(
        session,
        action="settings.smtp",
        source=activity.SOURCE_WEB,
        employee=_as_employee(actor),
        user=_as_user(actor),
        target=payload.host or "—",
    )
    config = await site_settings.smtp_config(session)
    return SmtpConfigPublic(**site_settings.smtp_config_public(config))


@router.post("/admin/settings/smtp/test")
async def send_test_email(
    payload: SmtpTestRequest,
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Queue one test letter.

    The only way to find out whether mail actually works is to send some. Doing it here
    rather than at the first forgotten password means the person who can fix the settings
    is the one who sees the failure.
    """
    config = await site_settings.smtp_config(session)
    if not config.get("host"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pochta serveri sozlanmagan — avval SMTP manzilini saqlang.",
        )

    await activity.record(
        session,
        action="settings.smtp.test",
        source=activity.SOURCE_WEB,
        employee=_as_employee(actor),
        user=_as_user(actor),
        target=payload.to_address,
    )
    await session.commit()

    pool = await get_arq_pool()
    await pool.enqueue_job("send_test_email", payload.to_address)
    return {
        "message": (
            f"Sinov xati {payload.to_address} manziliga navbatga qo'yildi. "
            "Bir daqiqada yetib bormasa, worker loglarini tekshiring."
        )
    }


# --------------------------------------------------------------------------- activity


@router.get("/admin/activity", response_model=list[ActivityEventResponse])
async def list_activity(
    source: str | None = None,
    action: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, le=500),
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> list[ActivityEventResponse]:
    """The newest events, filtered."""
    stmt = select(ActivityEvent)
    if source:
        stmt = stmt.where(ActivityEvent.source == source)
    if action:
        stmt = stmt.where(ActivityEvent.action == action)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(ActivityEvent.actor_name.ilike(like), ActivityEvent.target.ilike(like))
        )
    stmt = stmt.order_by(ActivityEvent.created_at.desc()).limit(limit)

    rows = (await session.execute(stmt)).scalars()
    return [ActivityEventResponse(**activity.describe(event)) for event in rows]


@router.get("/admin/activity/daily", response_model=list[ActivityDay])
async def activity_by_day(
    days: int = Query(default=30, ge=1, le=180),
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> list[ActivityDay]:
    """How many distinct people used each side of the system, per day.

    Distinct *employees*, not events: a staffer who pressed forty buttons is one user, and
    counting the presses would make a quiet day with one busy person look like a crowd.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    day = func.date_trunc("day", ActivityEvent.created_at).label("day")

    rows = (
        await session.execute(
            select(
                day,
                ActivityEvent.source,
                func.count(func.distinct(ActivityEvent.employee_id)).label("users"),
                func.count().label("events"),
            )
            .where(ActivityEvent.created_at >= since)
            .group_by(day, ActivityEvent.source)
            .order_by(day)
        )
    ).all()

    buckets: dict[str, ActivityDay] = {}
    for day_value, source, users, events in rows:
        key = day_value.date().isoformat()
        entry = buckets.setdefault(key, ActivityDay(day=key))
        if source == activity.SOURCE_BOT:
            entry.bot_users = users
            entry.bot_events = events
        else:
            entry.web_users = users
            entry.web_events = events

    return [buckets[key] for key in sorted(buckets)]


@router.get("/admin/activity/actors", response_model=list[ActorActivity])
async def last_action_per_person(
    days: int = Query(default=30, ge=1, le=180),
    limit: int = Query(default=100, le=500),
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> list[ActorActivity]:
    """Everybody who has done anything lately, and the last thing they did.

    DISTINCT ON is Postgres doing in one pass what would otherwise be a window function or
    a self-join: order by person then by time descending, keep the first row per person.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    latest = (
        await session.execute(
            select(ActivityEvent)
            .where(ActivityEvent.employee_id.isnot(None), ActivityEvent.created_at >= since)
            .order_by(ActivityEvent.employee_id, ActivityEvent.created_at.desc())
            .distinct(ActivityEvent.employee_id)
        )
    ).scalars().all()

    counts = dict(
        (
            await session.execute(
                select(ActivityEvent.employee_id, func.count())
                .where(ActivityEvent.employee_id.isnot(None), ActivityEvent.created_at >= since)
                .group_by(ActivityEvent.employee_id)
            )
        ).all()
    )

    people = [
        ActorActivity(
            employee_id=event.employee_id,
            actor_name=event.actor_name or "—",
            last_action=event.action,
            last_action_label=activity.action_label(event.action),
            last_target=event.target,
            last_source=event.source,
            last_seen_at=event.created_at,
            events=counts.get(event.employee_id, 0),
        )
        for event in latest
    ]
    people.sort(key=lambda p: p.last_seen_at, reverse=True)
    return people[:limit]


# --------------------------------------------------------------------------- public


@router.get("/site-settings", response_model=SiteConfigPublic)
async def public_site_settings(session: AsyncSession = Depends(get_db)) -> SiteConfigPublic:
    """The site's own descriptive text, for the browser tab and the login page.

    Deliberately unauthenticated and deliberately narrow: a title and a description are
    what a login page needs before anybody has signed in, and nothing here is private.
    """
    config = await site_settings.site_config(session)
    return SiteConfigPublic(
        title=config["title"],
        description=config["description"],
        organization=config["organization"],
    )
