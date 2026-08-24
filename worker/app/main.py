import logging

from arq.connections import RedisSettings

from afu_shared.settings import settings
from app.tasks.hemis_sync import hemis_sync_task
from app.tasks.notifications import notify_request_message, send_completion_notification
from app.tasks.oauth import notify_oauth_login_complete
from app.tasks.transient_cleanup import delete_telegram_message

logging.basicConfig(level=logging.INFO)


class WorkerSettings:
    functions = [
        hemis_sync_task,
        delete_telegram_message,
        send_completion_notification,
        notify_request_message,
        notify_oauth_login_complete,
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 4
    # HEMIS sync walks thousands of employees and downloads each one's photo; give it room to run.
    job_timeout = 1800
