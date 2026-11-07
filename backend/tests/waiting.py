import time
from collections.abc import Callable


def wait_until(condition: Callable[[], bool], timeout: float = 5.0, interval: float = 0.02) -> None:
    """Poll until `condition()` holds; fail the test after `timeout` seconds."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"condition not met within {timeout}s")
        time.sleep(interval)
