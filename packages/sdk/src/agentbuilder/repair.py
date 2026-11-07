"""Repair ladder step 2 (PLAN 4.4.2): retry transient failures with backoff. No NVIDIA packages, standard library only.

Steps 1 and 3 live where the model's text is parsed (the NAT adapter, packages/sdk-nat). This step is for calls the SDK
makes itself, such as the model check. It never retries a failure that waiting cannot fix (a bad key, a missing model),
and it gives up at once when the server asks for a wait longer than `max_wait` (an exhausted daily quota)."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import TypeVar

T = TypeVar("T")

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def retry_delay(attempt: int, retry_after: str | None, *, max_wait: float) -> float | None:
    """Seconds to wait before retry number `attempt` (0, 1, ...), or None when waiting is pointless: the server asked
    for more than `max_wait`. Honours a numeric `Retry-After`; otherwise backs off 1 s, 2 s, 4 s, ..."""
    try:
        wait = float(retry_after) if retry_after is not None else 2.0**attempt
    except ValueError:  # an HTTP date or junk: use the backoff
        wait = 2.0**attempt
    return wait if 0 <= wait <= max_wait else None


def call_with_retry(
    call: Callable[[], tuple[int, Mapping[str, str], T]],
    *,
    retries: int = 2,
    max_wait: float = 10.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[int, Mapping[str, str], T]:
    """Run `call` -> (status, headers, body); repeat while the status is transient, up to `retries` more times."""
    for attempt in range(retries + 1):
        status, headers, body = call()
        if status not in RETRYABLE_STATUS or attempt == retries:
            return status, headers, body
        delay = retry_delay(attempt, headers.get("Retry-After"), max_wait=max_wait)
        if delay is None:
            return status, headers, body
        sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
