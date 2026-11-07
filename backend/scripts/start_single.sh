#!/usr/bin/env bash
# Run the whole backend in one container (Render's free plan allows one service):
# the API (after migrating and seeding, in the same process; it also serves the React app)
# and the Celery worker with embedded Beat. If either exits, the container exits and the
# platform restarts it.
set -euo pipefail

# The worker starts at a lower CPU priority so the site comes up first; until it is ready,
# statuses are still derived from the clock and the Beat sweep catches up afterwards.
nice -n 10 celery -A app.workers.celery_app worker --beat --pool solo -l info \
  -s /tmp/celerybeat-schedule &
python -m scripts.serve &   # migrate + seed + API (which also serves the React app)

wait -n
echo "A process exited; stopping the container so the platform restarts it." >&2
exit 1
