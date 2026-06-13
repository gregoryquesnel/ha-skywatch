"""Schema bootstrap + migration ladder.

These tests are the highest-stakes in the project — a defect here loses
or corrupts user data. Three layers of coverage:
  1. Fresh DB → run migrations → assert final schema shape.
  2. Legacy DB (mimicking ha-tinker sky_sightings.db) → migrate → assert
     rows preserved, missing columns added, missing indexes added,
     malformed photo URLs cleaned.
  3. Idempotency — run migrations twice; second run is a no-op.
"""

from __future__ import annotations

import sqlite3

from custom_components.skywatch.storage import open_db
from custom_components.skywatch.storage.migrations import (
    _column_exists,
    run_migrations,
)
from custom_components.skywatch.storage.schema import SCHEMA_VERSION


def _index_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA index_list({table})")}


def _user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


class TestFreshBootstrap:
    def test_user_version_set(self, db_conn: sqlite3.Connection) -> None:
        assert _user_version(db_conn) == SCHEMA_VERSION

    def test_all_tables_present(self, db_conn: sqlite3.Connection) -> None:
        rows = db_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {row[0] for row in rows}
        assert {"sightings", "entries", "airport_movements", "flight_positions"}.issubset(names)

    def test_sightings_has_v1_columns(self, db_conn: sqlite3.Connection) -> None:
        for col in (
            "exit_time",
            "entry_time",
            "callsign",
            "registration",
            "altitude_ft",
            "ground_speed_kt",
            "closest_km",
            "aircraft_photo",
            "heading",
            "vertical_speed",
            "on_ground",
        ):
            assert _column_exists(db_conn, "sightings", col), f"missing {col}"

    def test_hardened_indexes_present(self, db_conn: sqlite3.Connection) -> None:
        idx = _index_names(db_conn, "sightings")
        # Legacy install had only exit_time + callsign + airline_iata indexes.
        # v1 adds these to support military/overhead/route queries.
        assert "idx_sightings_aircraft_code" in idx
        assert "idx_sightings_altitude_closest" in idx
        assert "idx_sightings_origin" in idx
        assert "idx_sightings_destination" in idx
        assert "idx_sightings_registration" in idx


class TestLegacyUpgrade:
    def test_legacy_db_starts_at_version_0(self, legacy_db_conn: sqlite3.Connection) -> None:
        assert _user_version(legacy_db_conn) == 0

    def test_legacy_db_lacks_v1_columns(self, legacy_db_conn: sqlite3.Connection) -> None:
        for col in ("entry_time", "heading", "vertical_speed", "on_ground"):
            assert not _column_exists(legacy_db_conn, "sightings", col)

    def test_migration_preserves_existing_rows(self, legacy_db_conn: sqlite3.Connection) -> None:
        legacy_db_conn.execute(
            "INSERT INTO sightings(exit_time, callsign, aircraft_code) VALUES(?, ?, ?)",
            ("2026-06-01T12:00:00+00:00", "ACA123", "B738"),
        )
        legacy_db_conn.execute(
            "INSERT INTO sightings(exit_time, callsign, aircraft_code) VALUES(?, ?, ?)",
            ("2026-06-02T08:30:00+00:00", "WJA456", "B737"),
        )
        legacy_db_conn.commit()

        run_migrations(legacy_db_conn)

        count = legacy_db_conn.execute("SELECT COUNT(*) FROM sightings").fetchone()[0]
        assert count == 2
        row = legacy_db_conn.execute(
            "SELECT callsign, aircraft_code FROM sightings ORDER BY exit_time"
        ).fetchall()
        assert row[0]["callsign"] == "ACA123"
        assert row[1]["callsign"] == "WJA456"

    def test_migration_adds_missing_columns(self, legacy_db_conn: sqlite3.Connection) -> None:
        run_migrations(legacy_db_conn)
        for col in ("entry_time", "heading", "vertical_speed", "on_ground"):
            assert _column_exists(legacy_db_conn, "sightings", col)

    def test_migration_adds_hardened_indexes(self, legacy_db_conn: sqlite3.Connection) -> None:
        run_migrations(legacy_db_conn)
        idx = _index_names(legacy_db_conn, "sightings")
        assert "idx_sightings_aircraft_code" in idx
        assert "idx_sightings_altitude_closest" in idx
        assert "idx_sightings_registration" in idx

    def test_migration_cleans_doubled_https_photo_urls(
        self, legacy_db_conn: sqlite3.Connection
    ) -> None:
        legacy_db_conn.execute(
            "INSERT INTO sightings(exit_time, aircraft_photo) VALUES(?, ?)",
            ("2026-06-01T12:00:00+00:00", "https:https://cdn.jetphotos.com/200/x.jpg"),
        )
        legacy_db_conn.execute(
            "INSERT INTO airport_movements(event_time, direction, aircraft_photo) VALUES(?, ?, ?)",
            ("2026-06-01T12:00:00+00:00", "landed", "https:https://cdn.jetphotos.com/200/y.jpg"),
        )
        # Clean URL row — must not be modified.
        legacy_db_conn.execute(
            "INSERT INTO sightings(exit_time, aircraft_photo) VALUES(?, ?)",
            ("2026-06-02T12:00:00+00:00", "https://cdn.jetphotos.com/200/z.jpg"),
        )
        legacy_db_conn.commit()

        run_migrations(legacy_db_conn)

        rows = list(
            legacy_db_conn.execute("SELECT aircraft_photo FROM sightings ORDER BY exit_time")
        )
        assert rows[0]["aircraft_photo"] == "https://cdn.jetphotos.com/200/x.jpg"
        assert rows[1]["aircraft_photo"] == "https://cdn.jetphotos.com/200/z.jpg"
        mv = legacy_db_conn.execute("SELECT aircraft_photo FROM airport_movements").fetchone()
        assert mv["aircraft_photo"] == "https://cdn.jetphotos.com/200/y.jpg"

    def test_migration_sets_user_version(self, legacy_db_conn: sqlite3.Connection) -> None:
        run_migrations(legacy_db_conn)
        assert _user_version(legacy_db_conn) == SCHEMA_VERSION


class TestIdempotent:
    def test_second_run_is_noop(self, db_conn: sqlite3.Connection) -> None:
        # db_conn is already at SCHEMA_VERSION; running migrations again
        # must not raise (no duplicate-column-name errors) and must not
        # change the version.
        before = _user_version(db_conn)
        run_migrations(db_conn)
        run_migrations(db_conn)
        assert _user_version(db_conn) == before

    def test_open_db_twice_same_path(self, db_path):
        conn1 = open_db(db_path)
        conn1.close()
        # Reopening triggers migrations again on an already-migrated DB.
        conn2 = open_db(db_path)
        assert _user_version(conn2) == SCHEMA_VERSION
        conn2.close()
