import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RecordingScheduler:
    """Stands in for Celery: records the jobs services ask for."""

    starts: list[tuple[uuid.UUID, datetime]] = field(default_factory=list)
    closes: list[tuple[uuid.UUID, datetime]] = field(default_factory=list)

    def schedule_start(self, rfq_id: uuid.UUID, at: datetime) -> None:
        self.starts.append((rfq_id, at))

    def schedule_close(self, rfq_id: uuid.UUID, close_at: datetime) -> None:
        self.closes.append((rfq_id, close_at))
