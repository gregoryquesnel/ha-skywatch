"""Shared pytest fixtures for skywatch tests."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from custom_components.skywatch.storage import open_db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A unique DB path inside the pytest tmp_path — no schema applied yet."""
    return tmp_path / "skywatch.db"


@pytest.fixture
def db_conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    """A skywatch DB at SCHEMA_VERSION with row_factory=Row, ready to write."""
    conn = open_db(db_path)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def legacy_db_conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    """A DB that mimics the legacy ha-tinker sky_sightings.db shape.

    No PRAGMA user_version (defaults to 0). Missing skywatch v1 columns:
    entry_time, heading, vertical_speed, on_ground. Also missing the
    hardened indexes (aircraft_code, altitude_ft+closest_km, origin_iata,
    destination_iata, registration). Used to exercise the 0→1 migration.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE sightings (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          exit_time TEXT NOT NULL,
          flight_number TEXT, callsign TEXT, airline TEXT, airline_iata TEXT,
          aircraft_code TEXT, aircraft_model TEXT, registration TEXT,
          origin_iata TEXT, origin_city TEXT,
          destination_iata TEXT, destination_city TEXT,
          altitude_ft INTEGER, ground_speed_kt INTEGER, closest_km REAL,
          aircraft_photo TEXT, tracked_by_device TEXT
        );
        CREATE INDEX idx_exit_time ON sightings(exit_time DESC);
        CREATE INDEX idx_callsign ON sightings(callsign);
        CREATE INDEX idx_airline_iata ON sightings(airline_iata);

        CREATE TABLE entries (
          flight_id TEXT PRIMARY KEY,
          entry_time TEXT NOT NULL,
          callsign TEXT, flight_number TEXT,
          aircraft_code TEXT, aircraft_model TEXT
        );
        CREATE INDEX idx_entries_entry_time ON entries(entry_time);

        CREATE TABLE airport_movements (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_time TEXT NOT NULL,
          direction TEXT NOT NULL,
          airport_iata TEXT,
          flight_number TEXT, callsign TEXT, airline TEXT, airline_iata TEXT,
          aircraft_code TEXT, aircraft_model TEXT, registration TEXT,
          origin_iata TEXT, destination_iata TEXT,
          aircraft_photo TEXT
        );
        CREATE INDEX idx_movement_time ON airport_movements(event_time DESC);
        CREATE INDEX idx_movement_airport ON airport_movements(airport_iata);
        CREATE INDEX idx_movement_direction ON airport_movements(direction);
    """)
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()
