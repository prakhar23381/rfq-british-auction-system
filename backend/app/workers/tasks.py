from app.workers.celery_app import celery_app


@celery_app.task(name="system.ping")
def ping() -> str:
    """Smoke-test task to verify the worker is consuming from the broker."""
    return "pong"
