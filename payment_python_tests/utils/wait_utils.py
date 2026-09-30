from __future__ import annotations

import time
from typing import Callable, TypeVar


T = TypeVar("T")


def wait_until(
    fetch: Callable[[], T],
    predicate: Callable[[T], bool],
    *,
    timeout: float = 30,
    interval: float = 0.5,
    description: str = "condition",
) -> T:
    deadline = time.monotonic() + timeout
    last: T | None = None
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            last = fetch()
            if predicate(last):
                return last
        except Exception as exc:
            last_error = exc
        time.sleep(interval)
    suffix = (
        f"; last error={last_error!r}"
        if last_error
        else f"; last value={last!r}"
    )
    raise TimeoutError(f"Timed out waiting for {description} ({timeout}s){suffix}")
