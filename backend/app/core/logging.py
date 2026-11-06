import logging

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging(level: str) -> None:
    """Plain structured-ish logs to stdout; uvicorn and Celery keep their own handlers."""
    logging.basicConfig(level=level.upper(), format=LOG_FORMAT)
