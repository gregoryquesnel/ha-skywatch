"""Forward-only schema migrations.

Versioning uses SQLite's PRAGMA user_version. A migration step is a function
that takes a connection at version N and brings it to N+1. The ladder is
called from connection bootstrap and is idempotent at every step — running
the same migration twice on the same DB must be a no-op.

Legacy DBs (ha-tinker sky_sightings.db) start at user_version=0 because
PRAGMA was never set; the 0→1 migration catches them up: missing columns
added via ALTER, missing indexes added via CREATE IF NOT EXISTS, and a
one-time historic-data cleanup of malformed photo URLs.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from .schema import BASE_SCHEMA_SQL, SCHEMA_VERSION


def _get_user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {int(version)}")


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, sql_type: str
) -> None:
    if not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")


def _migrate_0_to_1(conn: sqlite3.Connection) -> None:
    """Bootstrap or upgrade to v1.

    Order matters:
      1. executescript runs the v1 DDL — fresh installs get the full schema
         here; legacy DBs already have most tables but pick up missing
         indexes from CREATE INDEX IF NOT EXISTS.
      2. ALTER TABLE adds columns the legacy schema doesn't have.
      3. One-time UPDATE strips the 'https:https://' photo-URL corruption
         that recent FR24 builds emit for some rows. Idempotent — the
         WHERE clause excludes already-fixed rows.
    """
    conn.executescript(BASE_SCHEMA_SQL)
    _add_column_if_missing(conn, "sightings", "entry_time", "TEXT")
    _add_column_if_missing(conn, "sightings", "heading", "INTEGER")
    _add_column_if_missing(conn, "sightings", "vertical_speed", "INTEGER")
    _add_column_if_missing(conn, "sightings", "on_ground", "INTEGER")
    for table in ("sightings", "airport_movements"):
        conn.execute(
            f"UPDATE {table} "
            f"SET aircraft_photo = substr(aircraft_photo, 7) "
            f"WHERE aircraft_photo LIKE 'https:https://%'"
        )


MIGRATIONS: tuple[Callable[[sqlite3.Connection], None], ...] = (_migrate_0_to_1,)


def run_migrations(conn: sqlite3.Connection) -> int:
    """Catch a DB up to SCHEMA_VERSION. Returns the new user_version."""
    current = _get_user_version(conn)
    while current < SCHEMA_VERSION:
        MIGRATIONS[current](conn)
        current += 1
        _set_user_version(conn, current)
        conn.commit()
    return current
