from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "british_auction",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Auction tasks are idempotent; ack after running so a crashed worker's task is retried.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # ETA tasks (auction close) can sit in Redis for hours; avoid premature redelivery.
    broker_transport_options={"visibility_timeout": 43200},
    broker_connection_retry_on_startup=True,
)
