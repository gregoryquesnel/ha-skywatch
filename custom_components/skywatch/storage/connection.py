"""SQLite connection lifecycle.

Storage stays synchronous; the coordinator wraps each call in
hass.async_add_executor_job. The module-level `open_db` helper is the
single entry point used by tests and the coordinator alike.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Concatenate, ParamSpec, TypeVar

from .migrations import run_migrations


def open_db(path: Path) -> sqlite3.Connection:
    """Open (creating if missing) and migrate a skywatch DB.

    The parent directory must exist — the caller is responsible for
    `mkdir`ing it. Returns a Connection with row_factory=Row so callers
    can use column-name access in result dicts.

    check_same_thread=False lets HA's executor pool hand off the same
    connection across threads. That does NOT make concurrent use safe:
    HA's executor runs jobs in parallel on many threads, so callers must
    funnel every use of the connection through a SerializedConnection.
    """
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)
    return conn


P = ParamSpec("P")
R = TypeVar("R")


class SerializedConnection:
    """One sqlite3 connection, used by one thread at a time.

    The coordinator hands DB work to hass.async_add_executor_job, which
    runs jobs concurrently on a thread pool. A sqlite3.Connection carries
    a single transaction, so two threads interleaving on it corrupt each
    other's unit of work: one thread's commit() lands while the other is
    mid-statement ("cannot commit - no transaction is active",
    "bad parameter or other API misuse"), and the losing write — an
    exit's sighting row — is dropped. Every read and write goes through
    run(), which holds a lock for the whole unit of work and rolls back
    a transaction a failed unit left open, so the next caller starts
    clean instead of committing half of someone else's work.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.Lock()
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def run(
        self,
        fn: Callable[Concatenate[sqlite3.Connection, P], R],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        """Run fn(conn, *args, **kwargs) with exclusive use of the connection."""
        with self._lock:
            if self._closed:
                raise sqlite3.ProgrammingError("SerializedConnection is closed")
            try:
                return fn(self._conn, *args, **kwargs)
            except BaseException:
                if self._conn.in_transaction:
                    self._conn.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                self._conn.close()
