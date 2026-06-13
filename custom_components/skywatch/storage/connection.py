"""SQLite connection lifecycle.

Storage stays synchronous; the coordinator wraps each call in
hass.async_add_executor_job. The module-level `open_db` helper is the
single entry point used by tests and the coordinator alike.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .migrations import run_migrations


def open_db(path: Path) -> sqlite3.Connection:
    """Open (creating if missing) and migrate a skywatch DB.

    The parent directory must exist — the caller is responsible for
    `mkdir`ing it. Returns a Connection with row_factory=Row so callers
    can use column-name access in result dicts.

    check_same_thread=False lets HA's executor pool hand off the same
    connection across threads. The coordinator serializes all writes
    through hass.async_add_executor_job (one job at a time per executor
    pool), so concurrent-use safety is enforced at the call-site level
    rather than by sqlite's per-thread guard.
    """
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)
    return conn
