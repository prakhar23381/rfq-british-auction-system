import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RecordingScheduler:
    """Stands in for Celery: records the jobs services ask for."""

    starts: list[tuple[uuid.UUID, datetime]] = field(default_factory=list)
    closes: list[tuple[uuid.UUID, datetime]] = field(default_factory=list)

    def schedule_start(self, rfq_id: uuid.UUID, at: datetime) -> None:
        self.starts.append((rfq_id, at))

    def schedule_close(self, rfq_id: uuid.UUID, close_at: datetime) -> None:
        self.closes.append((rfq_id, close_at))


@dataclass
class Event:
    type: str
    channel: str
    data: dict[str, Any]


@dataclass
class RecordingPublisher:
    """Stands in for Redis pub/sub: records the live events services publish."""

    events: list[Event] = field(default_factory=list)

    def publish(self, type: str, channel: str, data: dict[str, Any]) -> None:
        # Round-trip through JSON like the real publisher, so payloads must be serialisable.
        self.events.append(Event(type, channel, json.loads(json.dumps(data))))

    def types(self) -> list[str]:
        return [e.type for e in self.events]

    def of_type(self, type: str) -> list[Event]:
        return [e for e in self.events if e.type == type]
