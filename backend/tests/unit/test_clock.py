from datetime import UTC, datetime

import pytest

from app.core.clock import FrozenClock, SystemClock


def test_frozen_clock_moves_only_when_told() -> None:
    clock = FrozenClock(datetime(2026, 11, 10, 17, 50, tzinfo=UTC))
    assert clock.now() == clock.now()
    assert clock.advance(minutes=10) == datetime(2026, 11, 10, 18, 0, tzinfo=UTC)


def test_clocks_are_timezone_aware() -> None:
    assert SystemClock().now().tzinfo is not None
    with pytest.raises(ValueError):
        FrozenClock(datetime(2026, 11, 10, 18, 0))


def test_durations_in_activity_messages() -> None:
    from datetime import timedelta

    from app.services.activity_service import duration

    assert duration(timedelta(minutes=5)) == "5 min"
    assert duration(timedelta(seconds=40)) == "40 s"
    assert duration(timedelta(minutes=2, seconds=30)) == "2 min 30 s"
    assert duration(timedelta(seconds=59.6)) == "1 min"
