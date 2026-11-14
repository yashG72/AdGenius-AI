"""Celery application.

Start a worker (from backend/, venv active). On Windows Celery's default process pool
is unsupported, so use the single-process "solo" pool:

    celery -A app.worker.celery_app worker --pool=solo --loglevel=info
"""

from celery import Celery

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
)

configure_logging(settings.log_level)
configure_tracing(settings)
