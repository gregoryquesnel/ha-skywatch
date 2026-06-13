"""SQLite schema DDL for skywatch v1.

The schema is the source of truth for what a fresh-install DB looks like.
Migrations from earlier shapes (including legacy ha-tinker sky_sightings.db
with no PRAGMA user_version) live in migrations.py and are responsible for
catching up an older DB to this same final state.

All indexes are part of the baseline so a fresh install never lacks them.
The legacy schema (ha-tinker pre-skywatch) was missing aircraft_code,
altitude_ft, closest_km, origin_iata, destination_iata indexes — those
are added here unconditionally so military/overhead/route queries no
longer require full table scans.
"""

from __future__ import annotations

from typing import Final

SCHEMA_VERSION: Final = 1

BASE_SCHEMA_SQL: Final = """
CREATE TABLE IF NOT EXISTS sightings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exit_time TEXT NOT NULL,
  entry_time TEXT,
  flight_number TEXT,
  callsign TEXT,
  airline TEXT,
  airline_iata TEXT,
  aircraft_code TEXT,
  aircraft_model TEXT,
  registration TEXT,
  origin_iata TEXT,
  origin_city TEXT,
  destination_iata TEXT,
  destination_city TEXT,
  altitude_ft INTEGER,
  ground_speed_kt INTEGER,
  closest_km REAL,
  aircraft_photo TEXT,
  tracked_by_device TEXT,
  heading INTEGER,
  vertical_speed INTEGER,
  on_ground INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sightings_exit_time ON sightings(exit_time DESC);
CREATE INDEX IF NOT EXISTS idx_sightings_callsign ON sightings(callsign);
CREATE INDEX IF NOT EXISTS idx_sightings_airline_iata ON sightings(airline_iata);
CREATE INDEX IF NOT EXISTS idx_sightings_aircraft_code ON sightings(aircraft_code);
CREATE INDEX IF NOT EXISTS idx_sightings_altitude_closest ON sightings(altitude_ft, closest_km);
CREATE INDEX IF NOT EXISTS idx_sightings_origin ON sightings(origin_iata);
CREATE INDEX IF NOT EXISTS idx_sightings_destination ON sightings(destination_iata);
CREATE INDEX IF NOT EXISTS idx_sightings_registration ON sightings(registration);

CREATE TABLE IF NOT EXISTS entries (
  flight_id TEXT PRIMARY KEY,
  entry_time TEXT NOT NULL,
  callsign TEXT,
  flight_number TEXT,
  aircraft_code TEXT,
  aircraft_model TEXT
);
CREATE INDEX IF NOT EXISTS idx_entries_entry_time ON entries(entry_time);

CREATE TABLE IF NOT EXISTS airport_movements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_time TEXT NOT NULL,
  direction TEXT NOT NULL,
  airport_iata TEXT,
  flight_number TEXT,
  callsign TEXT,
  airline TEXT,
  airline_iata TEXT,
  aircraft_code TEXT,
  aircraft_model TEXT,
  registration TEXT,
  origin_iata TEXT,
  destination_iata TEXT,
  aircraft_photo TEXT
);
CREATE INDEX IF NOT EXISTS idx_movements_event_time ON airport_movements(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_movements_airport ON airport_movements(airport_iata);
CREATE INDEX IF NOT EXISTS idx_movements_direction ON airport_movements(direction);

CREATE TABLE IF NOT EXISTS flight_positions (
  flight_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  PRIMARY KEY (flight_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_flight_positions_ts ON flight_positions(ts);
CREATE INDEX IF NOT EXISTS idx_flight_positions_flight ON flight_positions(flight_id);
"""

SIGHTING_COLUMNS_V1: Final = (
    "exit_time",
    "entry_time",
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
    "heading",
    "vertical_speed",
    "on_ground",
)
