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
