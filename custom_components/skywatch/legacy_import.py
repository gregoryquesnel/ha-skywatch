"""Pure-Python legacy ha-tinker sky_sightings.db import.

No HA imports — testable in isolation against tmp_path SQLite. The
services.py wrapper translates LegacyImportError to HomeAssistantError
for surfacing through HA's service-call layer.

Strategy: ATTACH DATABASE the source file, run column-by-column
INSERTs against the target's already-migrated v1 schema, run the
photo-URL fixup over the newly-inserted rows. Schema differences
between the legacy and v1 shape are absorbed by SELECTing only the
columns that exist on the source side — missing columns default to
NULL on the target (this is what skywatch v1 expects for legacy
imports anyway).
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path


class LegacyImportError(Exception):
    """Raised when the legacy DB cannot be imported safely."""


LEGACY_SIGHTINGS_COLUMNS = (
    "exit_time",
    "flight_number",
    "callsign",
    "airline",
    "airline_iata",
    "aircraft_code",
    "aircraft_model",
    "registration",
    "origin_iata",
    "origin_city",
    "destination_iata",
    "destination_city",
    "altitude_ft",
    "ground_speed_kt",
    "closest_km",
    "aircraft_photo",
    "tracked_by_device",
)

OPTIONAL_LEGACY_SIGHTINGS_COLUMNS = (
    "entry_time",
    "heading",
    "vertical_speed",
)

LEGACY_MOVEMENTS_COLUMNS = (
    "event_time",
    "direction",
    "airport_iata",
    "flight_number",
    "callsign",
    "airline",
    "airline_iata",
    "aircraft_code",
    "aircraft_model",
    "registration",
    "origin_iata",
    "destination_iata",
    "aircraft_photo",
)

LEGACY_ENTRIES_COLUMNS = (
    "flight_id",
    "entry_time",
    "callsign",
    "flight_number",
    "aircraft_code",
    "aircraft_model",
)


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the column names of a table. Accepts 'schema.name' too.

    SQLite's PRAGMA table_info takes the table name as an argument, but
    the schema (database alias for ATTACHed DBs) goes before the pragma
    name — `PRAGMA legacy.table_info(sightings)`, not the inverse.
    """
    if "." in table:
        schema, name = table.split(".", 1)
        sql = f"PRAGMA {schema}.table_info({name})"
    else:
        sql = f"PRAGMA table_info({table})"
    return {row[1] for row in conn.execute(sql)}


def _copy_table(
    conn: sqlite3.Connection,
    *,
    source_alias: str,
    table: str,
    required_columns: tuple[str, ...],
    optional_columns: tuple[str, ...] = (),
) -> int:
    """Copy rows from <source_alias>.<table> into main.<table>.

    Returns rowcount. Raises LegacyImportError if any required column
    is missing on the source side — the user has a non-ha-tinker DB or
    a partial schema and we should fail loud.
    """
    source_cols = _column_names(conn, f"{source_alias}.{table}")
    missing = set(required_columns) - source_cols
    if missing:
        raise LegacyImportError(
            f"Legacy {table} table is missing columns: {sorted(missing)}. "
            f"Refusing to import — manual fix required."
        )

    columns_to_copy = list(required_columns)
    columns_to_copy.extend(col for col in optional_columns if col in source_cols)

    cols_sql = ", ".join(columns_to_copy)
    cursor = conn.execute(
        f"INSERT INTO main.{table} ({cols_sql}) SELECT {cols_sql} FROM {source_alias}.{table}"
    )
    return cursor.rowcount


def import_legacy_db(
    target_conn: sqlite3.Connection,
    source_path: Path,
) -> dict[str, int]:
    """Copy legacy sky_sightings.db rows into the running skywatch DB.

    Commits the write transaction before DETACHing — SQLite refuses to
    DETACH a database while a write transaction is open against it, so
    the caller doesn't need to (and shouldn't) commit again on success.
    On error, target_conn is rolled back and the exception propagates;
    the legacy DB is still detached so the caller's connection stays
    clean.

    Returns a summary dict with per-table row counts.
    """
    if not source_path.exists():
        raise LegacyImportError(f"Source DB not found at {source_path}")

    target_conn.execute("ATTACH DATABASE ? AS legacy", (str(source_path),))
    try:
        existing_tables = {
            row[0]
            for row in target_conn.execute(
                "SELECT name FROM legacy.sqlite_master WHERE type='table'"
            )
        }
        for required in ("sightings", "entries", "airport_movements"):
            if required not in existing_tables:
                raise LegacyImportError(
                    f"Legacy DB has no '{required}' table — refusing to import."
                )

        sightings_inserted = _copy_table(
            target_conn,
            source_alias="legacy",
            table="sightings",
            required_columns=LEGACY_SIGHTINGS_COLUMNS,
            optional_columns=OPTIONAL_LEGACY_SIGHTINGS_COLUMNS,
        )
        entries_inserted = _copy_table(
            target_conn,
            source_alias="legacy",
            table="entries",
            required_columns=LEGACY_ENTRIES_COLUMNS,
        )
        movements_inserted = _copy_table(
            target_conn,
            source_alias="legacy",
            table="airport_movements",
            required_columns=LEGACY_MOVEMENTS_COLUMNS,
        )

        # Photo URL fixup over rows we just inserted. The skywatch
        # migration ladder already cleaned the target's pre-existing
        # rows; the legacy rows still carry the 'https:https://'
        # corruption from FR24's older builds.
        for table in ("sightings", "airport_movements"):
            target_conn.execute(
                f"UPDATE main.{table} "
                f"SET aircraft_photo = substr(aircraft_photo, 7) "
                f"WHERE aircraft_photo LIKE 'https:https://%'"
            )

        target_conn.commit()
    except BaseException:
        target_conn.rollback()
        # DETACH still required so we don't leave the attached alias
        # bound on the caller's connection. Suppress because the alias
        # may have failed to bind in the first place.
        with contextlib.suppress(sqlite3.OperationalError):
            target_conn.execute("DETACH DATABASE legacy")
        raise

    target_conn.execute("DETACH DATABASE legacy")
    return {
        "sightings_inserted": sightings_inserted,
        "entries_inserted": entries_inserted,
        "movements_inserted": movements_inserted,
    }
