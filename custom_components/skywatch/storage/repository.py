"""Write-side data access — insert sightings, entries, movements.

Synchronous; the coordinator wraps these in async_add_executor_job. Keeping
storage sync makes it trivially testable with tmp_path SQLite — no HA core
involvement, no async fixtures.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from ..const import DEFAULT_ENTRY_TTL_HOURS
from ..models import Entry, Movement, Sighting
from .normalizers import normalize_photo_url


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def insert_entry(conn: sqlite3.Connection, entry: Entry) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO entries
           (flight_id, entry_time, callsign, flight_number, aircraft_code, aircraft_model)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            entry.flight_id,
            _iso(entry.entry_time),
            entry.callsign,
            entry.flight_number,
            entry.aircraft_code,
            entry.aircraft_model,
        ),
    )


def prune_stale_entries(
    conn: sqlite3.Connection,
    now: datetime | None = None,
    ttl_hours: int = DEFAULT_ENTRY_TTL_HOURS,
) -> int:
    """Delete entries whose entry_time is older than ttl_hours from now.

    Returns the number of rows deleted. Called on every entry insert so
    orphan rows never accumulate even if a matching exit event is dropped.
    """
    if now is None:
        now = datetime.now(UTC)
    cutoff = (now - timedelta(hours=ttl_hours)).astimezone(UTC).isoformat(timespec="seconds")
    cursor = conn.execute("DELETE FROM entries WHERE entry_time < ?", (cutoff,))
    return cursor.rowcount


def take_entry_time(conn: sqlite3.Connection, flight_id: str | None) -> datetime | None:
    """Pop the matching entry_time for a flight_id (returns None if absent).

    Reads + deletes in one transaction — by the time the sighting is
    persisted, the entries row has served its purpose. Returning the time
    decoupled from the entries row also means callers don't need to keep
    track of cleanup.
    """
    if not flight_id:
        return None
    row = conn.execute(
        "SELECT entry_time FROM entries WHERE flight_id = ?", (flight_id,)
    ).fetchone()
    if row is None:
        return None
    conn.execute("DELETE FROM entries WHERE flight_id = ?", (flight_id,))
    iso = row[0] if not hasattr(row, "keys") else row["entry_time"]
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (AttributeError, ValueError, TypeError):
        return None


def insert_sighting(conn: sqlite3.Connection, sighting: Sighting) -> int:
    """Insert a sighting; returns the new row id."""
    cursor = conn.execute(
        """INSERT INTO sightings (
            exit_time, entry_time,
            flight_number, callsign, airline, airline_iata,
            aircraft_code, aircraft_model, registration,
            origin_iata, origin_city, destination_iata, destination_city,
            altitude_ft, ground_speed_kt, closest_km, aircraft_photo,
            tracked_by_device, heading, vertical_speed, on_ground
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            _iso(sighting.exit_time),
            _iso(sighting.entry_time) if sighting.entry_time else None,
            sighting.flight_number,
            sighting.callsign,
            sighting.airline,
            sighting.airline_iata,
            sighting.aircraft_code,
            sighting.aircraft_model,
            sighting.registration,
            sighting.origin_iata,
            sighting.origin_city,
            sighting.destination_iata,
            sighting.destination_city,
            sighting.altitude_ft,
            sighting.ground_speed_kt,
            sighting.closest_km,
            normalize_photo_url(sighting.aircraft_photo),
            sighting.tracked_by_device,
            sighting.heading,
            sighting.vertical_speed,
            None if sighting.on_ground is None else int(sighting.on_ground),
        ),
    )
    return int(cursor.lastrowid or 0)


def insert_movement(conn: sqlite3.Connection, movement: Movement) -> int:
    cursor = conn.execute(
        """INSERT INTO airport_movements (
            event_time, direction, airport_iata,
            flight_number, callsign, airline, airline_iata,
            aircraft_code, aircraft_model, registration,
            origin_iata, destination_iata, aircraft_photo
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            _iso(movement.event_time),
            movement.direction,
            movement.airport_iata,
            movement.flight_number,
            movement.callsign,
            movement.airline,
            movement.airline_iata,
            movement.aircraft_code,
            movement.aircraft_model,
            movement.registration,
            movement.origin_iata,
            movement.destination_iata,
            normalize_photo_url(movement.aircraft_photo),
        ),
    )
    return int(cursor.lastrowid or 0)
