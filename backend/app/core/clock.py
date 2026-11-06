"""Injectable clock. Services and domain code never call datetime.now() directly, so tests
can control time precisely (e.g. place a bid exactly at the trigger-window boundary)."""

from datetime import UTC, datetime, timedelta
from typing import Protocol


def utc_now() -> datetime:
    return datetime.now(UTC)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return utc_now()


class FrozenClock:
    """Test clock: returns a fixed time until moved with `set` or `advance`."""

    def __init__(self, at: datetime) -> None:
        self._now = _require_aware(at)

    def now(self) -> datetime:
        return self._now

    def set(self, at: datetime) -> None:
        self._now = _require_aware(at)

    def advance(self, **delta: float) -> datetime:
        self._now += timedelta(**delta)
        return self._now


def _require_aware(at: datetime) -> datetime:
    if at.tzinfo is None:
        raise ValueError("Clock times must be timezone-aware")
    return at


_system_clock = SystemClock()


def get_clock() -> Clock:
    """FastAPI dependency; tests override it with a FrozenClock."""
    return _system_clock
