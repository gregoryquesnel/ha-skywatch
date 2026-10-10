"""Legacy DB import — pure-function copy logic."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from custom_components.skywatch.legacy_import import (
    LegacyImportError,
    import_legacy_db,
    import_legacy_window,
)


@pytest.fixture
def legacy_source_path(tmp_path: Path) -> Path:
    """Build a legacy-shape sky_sightings.db with seeded rows."""
    db = tmp_path / "legacy_sky.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE sightings (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          exit_time TEXT NOT NULL,
          flight_number TEXT, callsign TEXT, airline TEXT, airline_iata TEXT,
          aircraft_code TEXT, aircraft_model TEXT, registration TEXT,
          origin_iata TEXT, origin_city TEXT,
          destination_iata TEXT, destination_city TEXT,
          altitude_ft INTEGER, ground_speed_kt INTEGER, closest_km REAL,
          aircraft_photo TEXT, tracked_by_device TEXT,
          entry_time TEXT, heading INTEGER, vertical_speed INTEGER
        );
        CREATE TABLE entries (
          flight_id TEXT PRIMARY KEY, entry_time TEXT NOT NULL,
          callsign TEXT, flight_number TEXT,
          aircraft_code TEXT, aircraft_model TEXT
        );
        CREATE TABLE airport_movements (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_time TEXT NOT NULL, direction TEXT NOT NULL,
          airport_iata TEXT,
          flight_number TEXT, callsign TEXT, airline TEXT, airline_iata TEXT,
          aircraft_code TEXT, aircraft_model TEXT, registration TEXT,
          origin_iata TEXT, destination_iata TEXT,
          aircraft_photo TEXT
        );

        INSERT INTO sightings(exit_time, callsign, aircraft_code, aircraft_photo)
          VALUES('2026-06-01T12:00:00+00:00', 'ACA123', 'B738',
                 'https:https://cdn.jetphotos.com/200/x.jpg');
        INSERT INTO sightings(exit_time, callsign, aircraft_code)
          VALUES('2026-06-02T08:30:00+00:00', 'WJA456', 'B737');
        INSERT INTO entries(flight_id, entry_time, callsign)
          VALUES('abc', '2026-06-13T19:00:00+00:00', 'ABC123');
        INSERT INTO airport_movements(event_time, direction, airport_iata, callsign)
          VALUES('2026-06-01T11:50:00+00:00', 'landed', 'YQR', 'WJA802');
    """)
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def legacy_missing_columns_path(tmp_path: Path) -> Path:
    """A legacy-ish DB missing required sightings columns."""
    db = tmp_path / "broken.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE sightings (id INTEGER PRIMARY KEY, exit_time TEXT);
        CREATE TABLE entries (flight_id TEXT PRIMARY KEY, entry_time TEXT);
        CREATE TABLE airport_movements (id INTEGER PRIMARY KEY, event_time TEXT, direction TEXT);
    """)
    conn.commit()
    conn.close()
    return db


def test_import_copies_all_rows(legacy_source_path: Path, db_conn: sqlite3.Connection) -> None:
    summary = import_legacy_db(db_conn, legacy_source_path)
    db_conn.commit()

    assert summary["sightings_inserted"] == 2
    assert summary["entries_inserted"] == 1
    assert summary["movements_inserted"] == 1

    assert db_conn.execute("SELECT COUNT(*) FROM sightings").fetchone()[0] == 2
    assert db_conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 1
    assert db_conn.execute("SELECT COUNT(*) FROM airport_movements").fetchone()[0] == 1


def test_import_preserves_existing_target_rows(
    legacy_source_path: Path, db_conn: sqlite3.Connection
) -> None:
    # Pre-insert a sighting in the target — must coexist with the imports.
    db_conn.execute(
        "INSERT INTO sightings(exit_time, callsign) VALUES(?, ?)",
        ("2026-06-13T20:00:00+00:00", "PRE_EXISTING"),
    )
    db_conn.commit()

    import_legacy_db(db_conn, legacy_source_path)
    db_conn.commit()

    total = db_conn.execute("SELECT COUNT(*) FROM sightings").fetchone()[0]
    assert total == 3
    pre = db_conn.execute(
        "SELECT COUNT(*) FROM sightings WHERE callsign = 'PRE_EXISTING'"
    ).fetchone()[0]
    assert pre == 1


def test_import_cleans_doubled_photo_url(
    legacy_source_path: Path, db_conn: sqlite3.Connection
) -> None:
    import_legacy_db(db_conn, legacy_source_path)
    db_conn.commit()

    row = db_conn.execute(
        "SELECT aircraft_photo FROM sightings WHERE aircraft_photo IS NOT NULL"
    ).fetchone()
    assert row["aircraft_photo"] == "https://cdn.jetphotos.com/200/x.jpg"


def test_missing_source_db_raises(db_conn: sqlite3.Connection, tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.db"
    with pytest.raises(LegacyImportError):
        import_legacy_db(db_conn, missing)


def test_legacy_db_missing_table_raises(db_conn: sqlite3.Connection, tmp_path: Path) -> None:
    db = tmp_path / "no_tables.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE wrong_table (x INTEGER)")
    conn.commit()
    conn.close()

    with pytest.raises(LegacyImportError):
        import_legacy_db(db_conn, db)


def test_legacy_db_missing_required_columns_raises(
    legacy_missing_columns_path: Path, db_conn: sqlite3.Connection
) -> None:
    with pytest.raises(LegacyImportError) as exc_info:
        import_legacy_db(db_conn, legacy_missing_columns_path)
    assert "missing columns" in str(exc_info.value)


# --- import_legacy_window -------------------------------------------------


def _seed_legacy_window(path: Path) -> None:
    """Append a spread of rows across a 'gap' to the legacy fixture DB."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        INSERT INTO sightings(exit_time, entry_time, callsign, registration, closest_km)
          VALUES('2026-07-01T10:00:00+00:00', '2026-07-01T09:50:00+00:00',
                 'GAP1', 'C-GAP1', 4.2);
        INSERT INTO sightings(exit_time, callsign, aircraft_photo)
          VALUES('2026-07-02T10:00:00+00:00', 'GAP2',
                 'https:https://cdn.jetphotos.com/200/y.jpg');
        -- Two distinct flights that share every identity column.
        INSERT INTO sightings(exit_time, callsign) VALUES('2026-07-03T10:00:00+00:00', 'Blocked');
        INSERT INTO sightings(exit_time, callsign) VALUES('2026-07-03T10:00:00+00:00', 'Blocked');
        INSERT INTO sightings(exit_time, callsign) VALUES('2026-10-10T20:30:00+00:00', 'AFTER');
        INSERT INTO airport_movements(event_time, direction, airport_iata, callsign)
          VALUES('2026-07-01T11:00:00+00:00', 'took_off', 'YQR', 'GAP1');
        INSERT INTO airport_movements(event_time, direction, airport_iata, callsign)
          VALUES('2026-10-10T20:40:00+00:00', 'landed', 'YQR', 'AFTER');
    """)
    conn.commit()
    conn.close()


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_window_imports_only_rows_inside_bounds(
    legacy_source_path: Path, db_conn: sqlite3.Connection
) -> None:
    _seed_legacy_window(legacy_source_path)

    summary = import_legacy_window(
        db_conn,
        legacy_source_path,
        since="2026-06-15T00:00:00+00:00",
        until="2026-10-10T20:00:00Z",
    )

    assert summary["sightings_candidates"] == 4
    assert summary["sightings_inserted"] == 4
    assert summary["airport_movements_inserted"] == 1
    callsigns = sorted(r[0] for r in db_conn.execute("SELECT callsign FROM sightings").fetchall())
    # Pre-window (ACA123/WJA456) and post-window (AFTER) rows are excluded;
    # both identical 'Blocked' rows are kept, as in the source.
    assert callsigns == ["Blocked", "Blocked", "GAP1", "GAP2"]
    assert _count(db_conn, "entries") == 0


def test_window_maps_columns_like_full_import(
    legacy_source_path: Path, db_conn: sqlite3.Connection
) -> None:
    _seed_legacy_window(legacy_source_path)
    import_legacy_window(db_conn, legacy_source_path, since="2026-06-15", until="2026-07-03")

    gap1 = db_conn.execute("SELECT * FROM sightings WHERE callsign = 'GAP1'").fetchone()
    assert gap1["entry_time"] == "2026-07-01T09:50:00+00:00"
    assert gap1["registration"] == "C-GAP1"
    assert gap1["closest_km"] == 4.2
    assert gap1["on_ground"] is None
    gap2 = db_conn.execute("SELECT * FROM sightings WHERE callsign = 'GAP2'").fetchone()
    assert gap2["aircraft_photo"] == "https://cdn.jetphotos.com/200/y.jpg"


def test_window_rerun_is_idempotent(legacy_source_path: Path, db_conn: sqlite3.Connection) -> None:
    _seed_legacy_window(legacy_source_path)
    first = import_legacy_window(db_conn, legacy_source_path)
    second = import_legacy_window(db_conn, legacy_source_path)

    assert first["sightings_inserted"] == 7
    assert second["sightings_inserted"] == 0
    assert second["sightings_skipped"] == 7
    assert second["airport_movements_inserted"] == 0
    assert _count(db_conn, "sightings") == 7
    assert _count(db_conn, "airport_movements") == 3


def test_window_skips_rows_already_written_by_full_import(
    legacy_source_path: Path, db_conn: sqlite3.Connection
) -> None:
    import_legacy_db(db_conn, legacy_source_path)
    summary = import_legacy_window(db_conn, legacy_source_path)

    assert summary["sightings_inserted"] == 0
    assert summary["airport_movements_inserted"] == 0
    assert _count(db_conn, "sightings") == 2


def test_window_dedupe_tolerates_writer_clock_skew(
    legacy_source_path: Path, db_conn: sqlite3.Connection
) -> None:
    """skywatch stamps the same event up to ~1 s before the legacy logger,
    and may lack entry_time; that row must still count as present."""
    db_conn.execute(
        "INSERT INTO sightings(exit_time, entry_time, callsign, aircraft_code) VALUES(?, ?, ?, ?)",
        ("2026-06-02T08:29:59+00:00", None, "WJA456", "B737"),
    )
    db_conn.commit()

    summary = import_legacy_window(db_conn, legacy_source_path, since="2026-06-02")
    assert summary["sightings_inserted"] == 0
    assert summary["sightings_skipped"] == 1

    strict = import_legacy_window(
        db_conn, legacy_source_path, since="2026-06-02", tolerance_seconds=0
    )
    assert strict["sightings_inserted"] == 1


def test_window_does_not_dedupe_on_differing_payload(
    legacy_source_path: Path, db_conn: sqlite3.Connection
) -> None:
    db_conn.execute(
        "INSERT INTO sightings(exit_time, callsign, aircraft_code) VALUES(?, ?, ?)",
        ("2026-06-02T08:30:00+00:00", "WJA456", "B38M"),
    )
    db_conn.commit()

    summary = import_legacy_window(db_conn, legacy_source_path, since="2026-06-02")
    assert summary["sightings_inserted"] == 1


def test_window_dry_run_writes_nothing(
    legacy_source_path: Path, db_conn: sqlite3.Connection
) -> None:
    _seed_legacy_window(legacy_source_path)
    summary = import_legacy_window(db_conn, legacy_source_path, dry_run=True)

    assert summary["sightings_inserted"] == 7
    assert summary["airport_movements_inserted"] == 3
    assert _count(db_conn, "sightings") == 0
    assert _count(db_conn, "airport_movements") == 0


def test_window_rejects_bad_bounds(legacy_source_path: Path, db_conn: sqlite3.Connection) -> None:
    with pytest.raises(LegacyImportError):
        import_legacy_window(db_conn, legacy_source_path, since="not-a-date")
    with pytest.raises(LegacyImportError):
        import_legacy_window(db_conn, legacy_source_path, since="2026-07-02", until="2026-07-01")
    # Connection is left usable (legacy alias detached, no open transaction).
    assert not db_conn.in_transaction
    assert "legacy" not in {r[1] for r in db_conn.execute("PRAGMA database_list")}
