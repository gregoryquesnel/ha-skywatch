"""Insert/select round-trip and entry-exit join semantics."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.skywatch.models import Entry, Movement, Sighting
from custom_components.skywatch.storage import (
    insert_entry,
    insert_movement,
    insert_sighting,
    prune_stale_entries,
    take_entry_time,
)


def _now() -> datetime:
    return datetime(2026, 6, 13, 20, 30, 0, tzinfo=UTC)


class TestInsertSighting:
    def test_round_trip_full_payload(self, db_conn: sqlite3.Connection) -> None:
        sighting = Sighting(
            exit_time=_now(),
            entry_time=_now() - timedelta(minutes=12),
            flight_number="ACA123",
            callsign="ACA123",
            airline="Air Canada",
            airline_iata="AC",
            aircraft_code="B738",
            aircraft_model="Boeing 737-8 MAX",
            registration="C-FGAR",
            origin_iata="YYC",
            origin_city="Calgary",
            destination_iata="YVR",
            destination_city="Vancouver",
            altitude_ft=10500,
            ground_speed_kt=450,
            closest_km=3.5,
            aircraft_photo="https://cdn.jetphotos.com/200/x.jpg",
            tracked_by_device="dev_123",
            heading=270,
            vertical_speed=1200,
            on_ground=False,
        )
        row_id = insert_sighting(db_conn, sighting)
        assert row_id > 0

        row = db_conn.execute("SELECT * FROM sightings WHERE id = ?", (row_id,)).fetchone()
        assert row["callsign"] == "ACA123"
        assert row["airline"] == "Air Canada"
        assert row["closest_km"] == pytest.approx(3.5)
        assert row["heading"] == 270
        assert row["on_ground"] == 0

    def test_strips_doubled_photo_prefix_at_insert(self, db_conn: sqlite3.Connection) -> None:
        sighting = Sighting(
            exit_time=_now(),
            aircraft_photo="https:https://cdn.jetphotos.com/200/x.jpg",
        )
        insert_sighting(db_conn, sighting)
        row = db_conn.execute("SELECT aircraft_photo FROM sightings").fetchone()
        assert row["aircraft_photo"] == "https://cdn.jetphotos.com/200/x.jpg"

    def test_handles_nullable_fields(self, db_conn: sqlite3.Connection) -> None:
        sighting = Sighting(exit_time=_now())
        row_id = insert_sighting(db_conn, sighting)
        row = db_conn.execute("SELECT * FROM sightings WHERE id = ?", (row_id,)).fetchone()
        assert row["callsign"] is None
        assert row["altitude_ft"] is None
        assert row["closest_km"] is None
        assert row["on_ground"] is None


class TestEntriesLifecycle:
    def test_insert_then_take_returns_entry_time(self, db_conn: sqlite3.Connection) -> None:
        entry_time = _now() - timedelta(minutes=8)
        insert_entry(
            db_conn,
            Entry(flight_id="abc123", entry_time=entry_time, callsign="ACA123"),
        )
        taken = take_entry_time(db_conn, "abc123")
        assert taken is not None
        assert taken.tzinfo is not None
        assert int(taken.timestamp()) == int(entry_time.timestamp())

    def test_take_removes_row(self, db_conn: sqlite3.Connection) -> None:
        insert_entry(db_conn, Entry(flight_id="abc123", entry_time=_now()))
        take_entry_time(db_conn, "abc123")
        assert (
            db_conn.execute("SELECT COUNT(*) FROM entries WHERE flight_id = 'abc123'").fetchone()[0]
            == 0
        )

    def test_take_returns_none_for_missing(self, db_conn: sqlite3.Connection) -> None:
        assert take_entry_time(db_conn, "missing_id") is None

    def test_take_returns_none_for_empty_flight_id(self, db_conn: sqlite3.Connection) -> None:
        assert take_entry_time(db_conn, None) is None
        assert take_entry_time(db_conn, "") is None

    def test_replace_on_duplicate(self, db_conn: sqlite3.Connection) -> None:
        e1 = Entry(flight_id="abc", entry_time=_now(), callsign="OLD")
        e2 = Entry(flight_id="abc", entry_time=_now(), callsign="NEW")
        insert_entry(db_conn, e1)
        insert_entry(db_conn, e2)
        row = db_conn.execute("SELECT callsign FROM entries WHERE flight_id = 'abc'").fetchone()
        assert row["callsign"] == "NEW"

    def test_prune_removes_stale(self, db_conn: sqlite3.Connection) -> None:
        now = _now()
        # Fresh: within TTL.
        insert_entry(db_conn, Entry(flight_id="fresh", entry_time=now - timedelta(minutes=30)))
        # Stale: older than 2h default.
        insert_entry(db_conn, Entry(flight_id="stale", entry_time=now - timedelta(hours=3)))

        deleted = prune_stale_entries(db_conn, now=now)
        assert deleted == 1
        remaining = {row[0] for row in db_conn.execute("SELECT flight_id FROM entries")}
        assert remaining == {"fresh"}


class TestInsertMovement:
    def test_round_trip_landing(self, db_conn: sqlite3.Connection) -> None:
        m = Movement(
            event_time=_now(),
            direction="landed",
            airport_iata="YQR",
            callsign="WJA802",
            aircraft_code="B737",
        )
        row_id = insert_movement(db_conn, m)
        row = db_conn.execute("SELECT * FROM airport_movements WHERE id = ?", (row_id,)).fetchone()
        assert row["direction"] == "landed"
        assert row["airport_iata"] == "YQR"
        assert row["callsign"] == "WJA802"

    def test_round_trip_takeoff(self, db_conn: sqlite3.Connection) -> None:
        m = Movement(
            event_time=_now(),
            direction="took_off",
            airport_iata="YQR",
            callsign="WJA803",
        )
        insert_movement(db_conn, m)
        row = db_conn.execute("SELECT direction FROM airport_movements").fetchone()
        assert row["direction"] == "took_off"
