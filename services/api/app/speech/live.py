"""In-process "latest partial" per session, for display only.

Partial recognition results are guesses that change as more audio arrives. They are never stored
and never become clinical facts. This store is process-local, so with several API workers a
client may sometimes see no partial; that is acceptable for a display nicety. A shared store
(Redis) can replace it in Phase 7 without changing callers.
"""

import time
import uuid
from dataclasses import dataclass

_TTL_SECONDS = 6.0


@dataclass(frozen=True)
class LivePartial:
    text: str
    speaker_id: str | None
    language: str | None


_store: dict[uuid.UUID, tuple[float, LivePartial]] = {}


def set_partial(interaction_id: uuid.UUID, partial: LivePartial) -> None:
    _store[interaction_id] = (time.monotonic(), partial)


def get_partial(interaction_id: uuid.UUID) -> LivePartial | None:
    entry = _store.get(interaction_id)
    if entry is None:
        return None
    if time.monotonic() - entry[0] > _TTL_SECONDS:
        _store.pop(interaction_id, None)
        return None
    return entry[1]


def clear(interaction_id: uuid.UUID) -> None:
    _store.pop(interaction_id, None)
