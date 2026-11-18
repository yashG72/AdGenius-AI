"""Celery application.

Two queues, so a long campaign run (minutes of LLM calls) never delays document
indexing or housekeeping:

- `default`   - documents.ingest, documents.cleanup, maintenance.*  (short jobs)
- `campaigns` - campaigns.execute                                    (long jobs)

Start workers from backend/ (venv active). On Windows Celery's default process pool is
unsupported, so use the single-process "solo" pool - one worker per queue:

    celery -A app.worker.celery_app worker --pool=solo -Q default -n default@%h --loglevel=info
    celery -A app.worker.celery_app worker --pool=solo -Q campaigns -n campaigns@%h --loglevel=info

(One worker can also serve both: `-Q default,campaigns`.) Periodic housekeeping needs
the scheduler process too:

    celery -A app.worker.celery_app beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.tracing import configure_tracing

settings = get_settings()

celery_app = Celery(
    "adgenius",
    broker=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    # Job state lives in PostgreSQL (e.g. brand_documents.status), so Celery's own
    # result store is unnecessary - and skipping it avoids an extra Redis round trip.
    task_ignore_result=True,
    # Fail fast when Redis is down, so publishing never stalls an HTTP request.
    broker_connection_timeout=2,
    broker_transport_options={
        "socket_connect_timeout": 2,
        "socket_timeout": 5,
        "max_retries": 1,
        "interval_start": 0,
        "interval_step": 0.2,
        "interval_max": 0.5,
    },
    # Reliability: acknowledge a task only AFTER it finishes, so a worker crash causes
    # redelivery instead of silent loss. Tasks are idempotent, so redelivery is safe.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # long tasks: don't hoard queued work
    # Timeouts: soft limit raises inside the task, hard limit kills it.
    task_soft_time_limit=15 * 60,
    task_time_limit=20 * 60,
    broker_connection_retry_on_startup=True,
    worker_hijack_root_logger=False,
    # ---------- Queues ----------
    task_default_queue="default",
    task_routes={"campaigns.*": {"queue": "campaigns"}},
    # ---------- Periodic jobs (run by `celery beat`) ----------
    beat_schedule={
        "purge-expired-refresh-tokens": {
            "task": "maintenance.purge_refresh_tokens",
            "schedule": crontab(hour=3, minute=17),  # daily, off the hour
        },
    },
)

configure_logging(settings.log_level)
configure_tracing(settings)
