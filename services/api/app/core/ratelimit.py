"""Sliding-window rate limits: a brake on password guessing from one address and on bulk patient
look-ups by one account.

Two stores behave the same. `RateLimiter` keeps the window in this process's memory: with several
workers or containers the effective limit is the number of workers times the setting, and a restart
clears it. `RedisRateLimiter`, used when `AAROGYA_REDIS_URL` is set, keeps it in Redis, so the limit
holds across every process and survives restarts of the API.

It is a brake, not the only defence: accounts still lock after repeated failures and every search is
audited. So if Redis cannot be reached the request is allowed and the failure is logged and counted,
rather than stopping a clinic from signing in.
"""

import logging
import time
import uuid
from collections import defaultdict, deque
from typing import Any, Protocol

from fastapi import Request

from app.core.errors import TooManyRequests

log = logging.getLogger("aarogya.ratelimit")


class Limiter(Protocol):
    def check(
        self, key: str, *, limit: int, window_seconds: float, now: float | None = None
    ) -> None: ...


def _refuse(retry: int) -> TooManyRequests:
    return TooManyRequests(
        f"Too many attempts. Wait {retry} seconds and try again.",
        extra={"retry_after_seconds": retry},
    )


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
            raise _refuse(int(window_seconds - (t - hits[0])) + 1)
        hits.append(t)
        if len(self._hits) > 10_000:  # forget idle keys so memory stays bounded
            for k in [k for k, v in self._hits.items() if not v or v[-1] <= t - window_seconds]:
                del self._hits[k]


# One round trip, atomic: drop hits older than the window, then either refuse (returning the age of
# the oldest hit) or record this one. Redis's own clock is used, so every API host agrees on time.
_SLIDING_WINDOW = """
local now
if ARGV[3] ~= '' then
  now = tonumber(ARGV[3])
else
  local t = redis.call('TIME')
  now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
end
local window = tonumber(ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  return now - tonumber(oldest[2])
end
redis.call('ZADD', KEYS[1], now, ARGV[4])
redis.call('PEXPIRE', KEYS[1], window)
return -1
"""


class RedisRateLimiter:
    def __init__(self, client: Any, *, prefix: str = "aarogya:rl:") -> None:
        self._redis = client
        self._script = client.register_script(_SLIDING_WINDOW)
        self._prefix = prefix
        self.unavailable = 0  # how many checks were let through because Redis could not answer

    @classmethod
    def from_url(cls, url: str) -> "RedisRateLimiter":
        import redis

        return cls(redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5))

    def check(
        self, key: str, *, limit: int, window_seconds: float, now: float | None = None
    ) -> None:
        if limit <= 0:
            return
        window_ms = max(1, int(window_seconds * 1000))
        args = [window_ms, limit, "" if now is None else int(now * 1000), uuid.uuid4().hex]
        try:
            age_ms = int(self._script(keys=[self._prefix + key], args=args))
        except Exception as exc:  # any Redis or network failure: let the request through
            self.unavailable += 1
            log.warning(
                "rate limit store unavailable; request allowed", extra={"error": type(exc).__name__}
            )
            return
        if age_ms >= 0:
            raise _refuse(int((window_ms - age_ms) / 1000) + 1)


def limiter_from_url(redis_url: str) -> Limiter:
    return RedisRateLimiter.from_url(redis_url) if redis_url else RateLimiter()


def limiter_of(request: Request) -> Limiter:
    limiter: Limiter = request.app.state.rate_limiter
    return limiter
