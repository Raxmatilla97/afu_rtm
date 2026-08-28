import logging

from arq import cron
from arq.connections import RedisSettings

from afu_shared.settings import settings
from app.tasks.group import (
    publish_request_card,
    refresh_request_cards,
    send_request_files_to_chat,
)
from app.tasks.email import send_password_reset_email, send_test_email
from app.tasks.activity_cleanup import prune_activity_events
from app.tasks.hemis_sync import hemis_sync_task
from app.tasks.notifications import (
    notify_request_assigned,
    notify_request_message,
    notify_request_returned,
    notify_request_waiting,
    send_completion_notification,
)
from app.tasks.oauth import notify_oauth_login_complete
from app.tasks.overdue import check_overdue_requests
from app.tasks.transient_cleanup import delete_telegram_message

logging.basicConfig(level=logging.INFO)


class WorkerSettings:
    functions = [
        hemis_sync_task,
        delete_telegram_message,
        send_password_reset_email,
        send_test_email,
        prune_activity_events,
        send_completion_notification,
        notify_request_message,
        notify_request_assigned,
        notify_request_returned,
        notify_request_waiting,
        notify_oauth_login_complete,
        publish_request_card,
        refresh_request_cards,
        send_request_files_to_chat,
        check_overdue_requests,
    ]
    #: Every half hour. Frequent enough that "late" means late rather than "late this
    #: morning", infrequent enough that a quiet night costs 48 empty queries.
    cron_jobs = [
        cron(check_overdue_requests, minute={0, 30}, run_at_startup=False),
        # Nightly, off-hours: the activity feed is a feed, not an archive.
        cron(prune_activity_events, hour={3}, minute={17}, run_at_startup=False),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 4
    # HEMIS sync walks thousands of employees and downloads each one's photo; give it room to run.
    job_timeout = 1800
