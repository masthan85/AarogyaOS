"""One live instance at a time.

Live transcript state and the duplicate-connection guard are held in process memory, so a second
worker or a second container would split recordings between processes that cannot see each other.
"One container" does not guarantee one worker, and a platform can start a second replica without
being asked, so the rule is enforced rather than assumed: each process tries to take a PostgreSQL
advisory lock for as long as it lives. The one that holds it is the active instance. Any other
reports itself as not ready and refuses audio connections.

The lock belongs to a database connection, so it is released automatically when the process dies,
however it dies. Redis would let state be shared; it would not make this check unnecessary until
shared session coordination is built and tested.
"""

import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

log = logging.getLogger("aarogya.instance")
# An arbitrary constant naming this lock. Changing it would let an old and a new build run together.
LOCK_KEY = 4_117_302_019


class InstanceLock:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._connection: Connection | None = None

    def acquire(self) -> bool:
        """Try to become the active instance. Safe to call again; never blocks."""
        if self._alive():
            return True
        self.release()
        try:
            connection = self._engine.connect().execution_options(isolation_level="AUTOCOMMIT")
            got = bool(
                connection.execute(
                    text("select pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}
                ).scalar()
            )
        except Exception:  # noqa: BLE001  (an unreachable database means "not the active instance")
            return False
        if not got:
            connection.close()
            return False
        self._connection = connection
        return True

    def held(self) -> bool:
        """True while this process is the active instance. Re-acquires after a lost connection."""
        return self._alive() or self.acquire()

    def release(self) -> None:
        if self._connection is not None:
            try:
                self._connection.invalidate()
                self._connection.close()
            except Exception:  # noqa: BLE001, S110  (closing a dead connection is best effort)
                pass
            self._connection = None

    def _alive(self) -> bool:
        if self._connection is None:
            return False
        try:
            self._connection.execute(text("select 1"))
        except Exception:  # noqa: BLE001  (the connection died, and the lock went with it)
            return False
        return True
