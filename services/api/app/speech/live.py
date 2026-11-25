"""Live recording state that is not stored in the database: the latest partial line of each session,
and which process holds each session's audio connection.

Partial recognition results are guesses that change as more audio arrives. They are shown while a
clinician watches and are never stored as clinical facts. The connection claim makes sure one
session has one audio connection at a time.

Two backends behave the same. The default keeps both in this process's memory, which is right for
a single API process. With `AAROGYA_REDIS_URL` set they live in Redis, so any process can show a
session's partial line and a second connection for the same session is refused whichever process it
reaches. A claim expires unless the process holding it renews it, so a process that dies does not
keep a session locked for longer than `CLAIM_SECONDS`.

If Redis cannot be reached, partials are skipped (a display nicety) and the claim falls back
to this process's memory, so a duplicate on the same process is still refused.
"""

import json
import logging
import threading
import time
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any, Protocol

log = logging.getLogger("aarogya.live")

PARTIAL_SECONDS = 6.0
CLAIM_SECONDS = 15.0
RENEW_EVERY_SECONDS = CLAIM_SECONDS / 3


@dataclass(frozen=True)
class LivePartial:
    text: str
    speaker_id: str | None
    language: str | None


class LiveBackend(Protocol):
    def set_partial(self, interaction_id: uuid.UUID, partial: LivePartial) -> None: ...
    def get_partial(self, interaction_id: uuid.UUID) -> LivePartial | None: ...
    def clear(self, interaction_id: uuid.UUID) -> None: ...
    def claim(self, interaction_id: uuid.UUID) -> str | None: ...
    def renew(self, interaction_id: uuid.UUID, token: str) -> bool: ...
    def release(self, interaction_id: uuid.UUID, token: str) -> None: ...
    def claimed(self, interaction_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]: ...


class MemoryLive:
    def __init__(self) -> None:
        self._partials: dict[uuid.UUID, tuple[float, LivePartial]] = {}
        self._claims: dict[uuid.UUID, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def set_partial(self, interaction_id: uuid.UUID, partial: LivePartial) -> None:
        self._partials[interaction_id] = (time.monotonic(), partial)

    def get_partial(self, interaction_id: uuid.UUID) -> LivePartial | None:
        entry = self._partials.get(interaction_id)
        if entry is None:
            return None
        if time.monotonic() - entry[0] > PARTIAL_SECONDS:
            self._partials.pop(interaction_id, None)
            return None
        return entry[1]

    def clear(self, interaction_id: uuid.UUID) -> None:
        self._partials.pop(interaction_id, None)

    def claim(self, interaction_id: uuid.UUID) -> str | None:
        now = time.monotonic()
        with self._lock:
            held = self._claims.get(interaction_id)
            if held is not None and held[0] > now:
                return None
            token = uuid.uuid4().hex
            self._claims[interaction_id] = (now + CLAIM_SECONDS, token)
            return token

    def renew(self, interaction_id: uuid.UUID, token: str) -> bool:
        with self._lock:
            held = self._claims.get(interaction_id)
            if held is None or held[1] != token:
                return False
            self._claims[interaction_id] = (time.monotonic() + CLAIM_SECONDS, token)
            return True

    def release(self, interaction_id: uuid.UUID, token: str) -> None:
        with self._lock:
            held = self._claims.get(interaction_id)
            if held is not None and held[1] == token:
                del self._claims[interaction_id]

    def claimed(self, interaction_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
        now = time.monotonic()
        return {i for i in interaction_ids if (c := self._claims.get(i)) is not None and c[0] > now}


# Delete or extend a claim only if this process still holds it.
_RELEASE = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0"
)
_RENEW = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('PEXPIRE', KEYS[1], ARGV[2]) end return 0"
)


class RedisLive:
    def __init__(self, client: Any, *, prefix: str = "aarogya:live:") -> None:
        self._redis = client
        self._prefix = prefix
        self._release = client.register_script(_RELEASE)
        self._renew = client.register_script(_RENEW)
        self._local = MemoryLive()  # used for claims while Redis cannot be reached
        self._fallback: set[uuid.UUID] = set()
        self.unavailable = 0

    @classmethod
    def from_url(cls, url: str) -> "RedisLive":
        import redis

        return cls(redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5))

    def _key(self, kind: str, interaction_id: uuid.UUID) -> str:
        return f"{self._prefix}{kind}:{interaction_id}"

    def _failed(self, what: str, exc: Exception) -> None:
        self.unavailable += 1
        log.warning("live state store unavailable", extra={"op": what, "error": type(exc).__name__})

    def set_partial(self, interaction_id: uuid.UUID, partial: LivePartial) -> None:
        try:
            self._redis.set(
                self._key("partial", interaction_id),
                json.dumps(asdict(partial)),
                px=int(PARTIAL_SECONDS * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            self._failed("set_partial", exc)

    def get_partial(self, interaction_id: uuid.UUID) -> LivePartial | None:
        try:
            raw = self._redis.get(self._key("partial", interaction_id))
        except Exception as exc:  # noqa: BLE001
            self._failed("get_partial", exc)
            return None
        return LivePartial(**json.loads(raw)) if raw else None

    def clear(self, interaction_id: uuid.UUID) -> None:
        try:
            self._redis.delete(self._key("partial", interaction_id))
        except Exception as exc:  # noqa: BLE001
            self._failed("clear", exc)

    def claim(self, interaction_id: uuid.UUID) -> str | None:
        token = uuid.uuid4().hex
        try:
            got = self._redis.set(
                self._key("claim", interaction_id), token, nx=True, px=int(CLAIM_SECONDS * 1000)
            )
        except Exception as exc:  # noqa: BLE001
            self._failed("claim", exc)
            local = self._local.claim(interaction_id)
            if local is not None:
                self._fallback.add(interaction_id)
            return local
        return token if got else None

    def renew(self, interaction_id: uuid.UUID, token: str) -> bool:
        if interaction_id in self._fallback:
            return self._local.renew(interaction_id, token)
        try:
            return bool(
                self._renew(
                    keys=[self._key("claim", interaction_id)],
                    args=[token, int(CLAIM_SECONDS * 1000)],
                )
            )
        except Exception as exc:  # noqa: BLE001
            self._failed("renew", exc)
            return True  # keep streaming; the claim expires on its own if this process is gone

    def release(self, interaction_id: uuid.UUID, token: str) -> None:
        if interaction_id in self._fallback:
            self._fallback.discard(interaction_id)
            self._local.release(interaction_id, token)
            return
        try:
            self._release(keys=[self._key("claim", interaction_id)], args=[token])
        except Exception as exc:  # noqa: BLE001
            self._failed("release", exc)

    def claimed(self, interaction_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
        ids = list(interaction_ids)
        if not ids:
            return set()
        try:
            values = self._redis.mget([self._key("claim", i) for i in ids])
        except Exception as exc:  # noqa: BLE001
            self._failed("claimed", exc)
            return set(ids)  # unknown: assume live rather than pause someone's recording
        return {i for i, v in zip(ids, values, strict=True) if v is not None}


_backend: LiveBackend = MemoryLive()


def configure(redis_url: str) -> LiveBackend:
    """Called once per app at start-up. Returns the backend now in use."""
    global _backend
    _backend = RedisLive.from_url(redis_url) if redis_url else MemoryLive()
    return _backend


def backend() -> LiveBackend:
    return _backend


def set_partial(interaction_id: uuid.UUID, partial: LivePartial) -> None:
    _backend.set_partial(interaction_id, partial)


def get_partial(interaction_id: uuid.UUID) -> LivePartial | None:
    return _backend.get_partial(interaction_id)


def clear(interaction_id: uuid.UUID) -> None:
    _backend.clear(interaction_id)


def claim(interaction_id: uuid.UUID) -> str | None:
    return _backend.claim(interaction_id)


def renew(interaction_id: uuid.UUID, token: str) -> bool:
    return _backend.renew(interaction_id, token)


def release(interaction_id: uuid.UUID, token: str) -> None:
    _backend.release(interaction_id, token)


def claimed(interaction_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    return _backend.claimed(interaction_ids)
