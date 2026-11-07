"""Single-container entry point: migrate, seed, then serve the API, all in one process.

Doing the three steps in one process loads the heavy libraries once instead of three times,
which roughly halves cold starts on a 0.1-CPU free instance (Render sleeps idle free services,
so every wake-up is a cold start).
"""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import uvicorn
from alembic.config import Config

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parent.parent


def migrate() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def seed() -> None:
    from app.core.clock import utc_now
    from app.db import SessionLocal
    from app.workers.scheduling import CeleryScheduler
    from scripts.seed import run

    with SessionLocal() as session:
        users, rfqs = run(session, wipe=False, now=utc_now(), scheduler=CeleryScheduler())
    print(f"Seeded {users} user(s) and {rfqs} RFQ(s).", flush=True)


def main(
    serve: Callable[..., Any] = uvicorn.run,
    steps: tuple[Callable[[], None], ...] = (migrate, seed),
) -> None:
    for step in steps:
        step()
    serve(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
