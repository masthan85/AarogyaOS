"""A small sliding-window rate limiter held in this process's memory.

It protects against password guessing from one address and against bulk patient look-ups by one
account. Limits are per worker process: with several workers or containers the effective limit is
the number of workers times the setting, and a restart clears it. A shared store (Redis) is needed
for exact limits across a fleet. It is a brake, not the only defence: accounts still lock after
repeated failures and every search is audited.
"""

import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.errors import TooManyRequests


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(
        self, key: str, *, limit: int, window_seconds: float, now: float | None = None
    ) -> None:
        """Record one attempt for `key`, or raise TooManyRequests when it exceeds `limit`."""
        if limit <= 0:
            return  # a limit of zero turns the check off
        t = time.monotonic() if now is None else now
        hits = self._hits[key]
        while hits and hits[0] <= t - window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            retry = int(window_seconds - (t - hits[0])) + 1
            raise TooManyRequests(
                f"Too many attempts. Wait {retry} seconds and try again.",
                extra={"retry_after_seconds": retry},
            )
        hits.append(t)
        if len(self._hits) > 10_000:  # forget idle keys so memory stays bounded
            for k in [k for k, v in self._hits.items() if not v or v[-1] <= t - window_seconds]:
                del self._hits[k]


def limiter_of(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter
