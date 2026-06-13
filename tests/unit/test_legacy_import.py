"""Legacy DB import — pure-function copy logic."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from custom_components.skywatch.legacy_import import (
    LegacyImportError,
    import_legacy_db,
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
