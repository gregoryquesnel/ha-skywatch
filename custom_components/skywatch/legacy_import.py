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
import time
from datetime import UTC, datetime
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


# --- Windowed, de-duplicating import --------------------------------------
#
# import_legacy_db() above is a one-shot copy: running it twice doubles
# every row, because `sightings` and `airport_movements` have no natural
# unique key (only an AUTOINCREMENT id). The windowed variant below is safe
# to re-run and is the tool for backfilling a gap — e.g. the period when
# skywatch's own FR24 handlers were silently dropping writes while the
# legacy ha-tinker logger kept recording the same events.
#
# Row identity: the legacy logger and skywatch both build their rows from
# the same flightradar24_* event payload with the same field mapping, so
# a legacy row and a skywatch row describe the same event when every
# payload-derived column is equal (NULL-safe) and the timestamps agree to
# within a couple of seconds. The legacy writer runs as a shell_command
# subprocess and stamps its row up to ~1 s after skywatch does. entry_time
# is excluded from the key: each writer keeps its own entries table, so a
# writer that started mid-flight records NULL where the other has a value.
#
# The `entries` table is deliberately not copied: it holds transient
# in-flight rows (TTL-pruned after a couple of hours) and copying them
# would collide with the running integration's own entries.

DEFAULT_DEDUPE_TOLERANCE_SECONDS = 2

_WINDOW_TABLES = (
    # (table, time column, required columns, optional columns)
    ("sightings", "exit_time", LEGACY_SIGHTINGS_COLUMNS, OPTIONAL_LEGACY_SIGHTINGS_COLUMNS),
    ("airport_movements", "event_time", LEGACY_MOVEMENTS_COLUMNS, ()),
)

# Columns that legitimately differ between two writers recording the same
# event, so they're left out of the identity comparison.
_NON_IDENTITY_COLUMNS = frozenset({"entry_time"})

_ISO_FMT = "%Y-%m-%dT%H:%M:%S+00:00"


def _to_utc_iso(value: str | datetime | None) -> str | None:
    """Normalize a bound to the stored timestamp shape (UTC, seconds, +00:00).

    Naive values are treated as UTC, matching parse_iso() elsewhere.
    Raises LegacyImportError on an unparseable string so a typo in a
    service call fails loud instead of silently importing everything.
    """
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as err:
            raise LegacyImportError(f"Unparseable timestamp bound: {value!r}") from err
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime(_ISO_FMT)


def _source_expr(column: str) -> str:
    """SELECT expression for a legacy column, with boundary normalization.

    aircraft_photo gets the same 'https:https://' fixup import_legacy_db
    applies via its post-insert UPDATE — done inline here so the dedupe
    comparison sees the normalized value the target actually stores.
    """
    if column == "aircraft_photo":
        return (
            "CASE WHEN l.aircraft_photo LIKE 'https:https://%' "
            "THEN substr(l.aircraft_photo, 7) ELSE l.aircraft_photo END"
        )
    return f"l.{column}"


def _window_plan(
    conn: sqlite3.Connection,
    *,
    source_alias: str,
    table: str,
    time_col: str,
    required_columns: tuple[str, ...],
    optional_columns: tuple[str, ...],
    since: str | None,
    until: str | None,
    tolerance_seconds: int,
) -> dict:
    """Build the SQL for one table's windowed, de-duplicated copy.

    Returns a dict with:
      candidates_sql — COUNT of legacy rows inside the window
      new_rows_sql   — the mapped legacy rows not yet in the target
      stage_table    — name of the TEMP table new rows are staged into
      commit_sql     — INSERT from the stage table into main, re-checking
                       identity so rows the live integration wrote after
                       staging are still skipped
      params         — bind parameters for candidates_sql / new_rows_sql
    """
    source_cols = _column_names(conn, f"{source_alias}.{table}")
    missing = set(required_columns) - source_cols
    if missing:
        raise LegacyImportError(
            f"Legacy {table} table is missing columns: {sorted(missing)}. "
            f"Refusing to import — manual fix required."
        )
    columns = list(required_columns)
    columns.extend(col for col in optional_columns if col in source_cols)

    where = []
    params: list[str] = []
    if since is not None:
        where.append(f"l.{time_col} >= ?")
        params.append(since)
    if until is not None:
        where.append(f"l.{time_col} < ?")
        params.append(until)
    window_sql = " AND ".join(where) if where else "1"

    tol = int(tolerance_seconds)
    identity = [
        f"t.{time_col} BETWEEN strftime('{_ISO_FMT}', l.{time_col}, '-{tol} seconds') "
        f"AND strftime('{_ISO_FMT}', l.{time_col}, '+{tol} seconds')"
    ]
    # Unary '+' keeps the planner off the per-column indexes (it otherwise
    # picks e.g. idx_sightings_altitude_closest, whose NULL/0 buckets are
    # huge) so every probe is a narrow range scan on the time index.
    identity.extend(
        f"+t.{col} IS {_source_expr(col)}"
        for col in columns
        if col != time_col and col not in _NON_IDENTITY_COLUMNS
    )
    not_dup = f"NOT EXISTS (SELECT 1 FROM main.{table} t WHERE {' AND '.join(identity)})"

    cols_sql = ", ".join(columns)
    select_sql = ", ".join(f"{_source_expr(col)} AS {col}" for col in columns)
    from_sql = f"FROM {source_alias}.{table} l WHERE {window_sql}"
    stage_table = f"_skywatch_import_{table}"
    return {
        "candidates_sql": f"SELECT COUNT(*) {from_sql}",
        "new_rows_sql": f"SELECT {select_sql} {from_sql} AND {not_dup} ORDER BY l.id",
        "stage_table": stage_table,
        # SQLite materializes an INSERT ... SELECT that reads its own
        # target table before inserting, so rows added by this statement
        # are invisible to its NOT EXISTS probe — legacy rows that are
        # genuinely distinct but share every identity column (rare, e.g.
        # two 'Blocked' flights exiting in the same second) are all kept,
        # exactly as the legacy DB holds them. _source_expr is idempotent,
        # so re-applying it to the already-normalized stage rows is safe.
        "commit_sql": (
            f"INSERT INTO main.{table} ({cols_sql}) "
            f"SELECT {cols_sql} FROM temp.{stage_table} l WHERE {not_dup} ORDER BY l.rowid"
        ),
        "params": tuple(params),
    }


def import_legacy_window(
    target_conn: sqlite3.Connection,
    source_path: Path,
    *,
    since: str | datetime | None = None,
    until: str | datetime | None = None,
    tolerance_seconds: int = DEFAULT_DEDUPE_TOLERANCE_SECONDS,
    dry_run: bool = False,
) -> dict[str, int]:
    """Copy legacy sightings + airport_movements in [since, until), skipping duplicates.

    Same column mapping as import_legacy_db(). A legacy row is skipped
    when the target already holds a row for the same event (see the
    module comment above for the identity rule). Both bounds are
    optional; with neither, the whole legacy DB is considered, which
    makes this a re-run-safe replacement for import_legacy_db().

    Built to run against a DB the integration is writing to. The
    expensive part — scanning the legacy window and probing for
    duplicates — runs as a plain read and stages the new rows in TEMP
    tables, so it never blocks the integration. Only the final copy runs
    under the write lock: one BEGIN IMMEDIATE transaction covering both
    tables, committed before the legacy DB is DETACHed. On error
    everything is rolled back. With dry_run=True nothing is written.

    Returns {"<table>_candidates", "<table>_inserted", "<table>_skipped"}
    for sightings and airport_movements, plus "write_lock_ms".
    """
    if not source_path.exists():
        raise LegacyImportError(f"Source DB not found at {source_path}")
    since_iso = _to_utc_iso(since)
    until_iso = _to_utc_iso(until)
    if since_iso and until_iso and since_iso >= until_iso:
        raise LegacyImportError(f"Empty window: since {since_iso} is not before until {until_iso}")

    if target_conn.in_transaction:
        target_conn.commit()
    target_conn.execute("ATTACH DATABASE ? AS legacy", (str(source_path),))
    summary: dict[str, int] = {}
    plans: list[tuple[str, dict]] = []
    try:
        _require_tables(target_conn, "legacy", [t for t, *_ in _WINDOW_TABLES])
        plans = [
            (
                table,
                _window_plan(
                    target_conn,
                    source_alias="legacy",
                    table=table,
                    time_col=time_col,
                    required_columns=required,
                    optional_columns=optional,
                    since=since_iso,
                    until=until_iso,
                    tolerance_seconds=tolerance_seconds,
                ),
            )
            for table, time_col, required, optional in _WINDOW_TABLES
        ]

        for table, plan in plans:
            summary[f"{table}_candidates"] = target_conn.execute(
                plan["candidates_sql"], plan["params"]
            ).fetchone()[0]
            if dry_run:
                summary[f"{table}_inserted"] = target_conn.execute(
                    f"SELECT COUNT(*) FROM ({plan['new_rows_sql']})", plan["params"]
                ).fetchone()[0]
            else:
                target_conn.execute(f"DROP TABLE IF EXISTS temp.{plan['stage_table']}")
                target_conn.execute(
                    f"CREATE TEMP TABLE {plan['stage_table']} AS {plan['new_rows_sql']}",
                    plan["params"],
                )

        if not dry_run:
            started = time.monotonic()
            target_conn.execute("BEGIN IMMEDIATE")
            for table, plan in plans:
                summary[f"{table}_inserted"] = target_conn.execute(plan["commit_sql"]).rowcount
            target_conn.commit()
            summary["write_lock_ms"] = int((time.monotonic() - started) * 1000)

        for table, _plan in plans:
            summary[f"{table}_skipped"] = (
                summary[f"{table}_candidates"] - summary[f"{table}_inserted"]
            )
    except BaseException:
        if target_conn.in_transaction:
            target_conn.rollback()
        _drop_stage_tables(target_conn, plans)
        with contextlib.suppress(sqlite3.OperationalError):
            target_conn.execute("DETACH DATABASE legacy")
        raise

    _drop_stage_tables(target_conn, plans)
    target_conn.execute("DETACH DATABASE legacy")
    return summary


def _require_tables(conn: sqlite3.Connection, alias: str, tables: list[str]) -> None:
    existing = {
        row[0] for row in conn.execute(f"SELECT name FROM {alias}.sqlite_master WHERE type='table'")
    }
    for table in tables:
        if table not in existing:
            raise LegacyImportError(f"Legacy DB has no '{table}' table — refusing to import.")


def _drop_stage_tables(conn: sqlite3.Connection, plans: list[tuple[str, dict]]) -> None:
    for _table, plan in plans:
        with contextlib.suppress(sqlite3.Error):
            conn.execute(f"DROP TABLE IF EXISTS temp.{plan['stage_table']}")
