"""Keeping the activity log a feed rather than an archive.

Every button press in the bot writes a row. At a few hundred staff that is thousands a day,
and none of it is worth keeping for a year: the panel shows the last month, and anything
older is answered better by the requests, messages and inventory movements — which are
records of what happened rather than of who looked at what.

Deleted in batches so a first run over a large backlog cannot hold one long transaction
open across the whole table.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from afu_shared.db import session_scope
from afu_shared.models import ActivityEvent

logger = logging.getLogger(__name__)

#: Comfortably longer than the panel's widest window (180 days is the API's maximum), so
#: pruning can never eat a range somebody can still ask for.
RETENTION_DAYS = 200
BATCH = 5000


async def prune_activity_events(ctx: dict) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    removed = 0

    while True:
        async with session_scope() as session:
            ids = (
                await session.execute(
                    select(ActivityEvent.id)
                    .where(ActivityEvent.created_at < cutoff)
                    .limit(BATCH)
                )
            ).scalars().all()
            if not ids:
                break
            await session.execute(delete(ActivityEvent).where(ActivityEvent.id.in_(ids)))
            removed += len(ids)

        if len(ids) < BATCH:
            break

    if removed:
        logger.info("Pruned %s activity events older than %s days", removed, RETENTION_DAYS)
