"""Trail position storage — insert / fetch / prune."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.skywatch.storage import (
    fetch_trails,
    insert_positions,
    prune_old_positions,
)


def _now() -> datetime:
    return datetime(2026, 6, 13, 20, 0, 0, tzinfo=UTC)


class TestInsertPositions:
    def test_inserts_multiple_rows(self, db_conn: sqlite3.Connection) -> None:
        now = _now()
        positions = [
            ("flight_A", now, 50.0, -104.0),
            ("flight_B", now, 50.1, -104.1),
            ("flight_A", now + timedelta(seconds=5), 50.01, -104.01),
        ]
        rowcount = insert_positions(db_conn, positions)
        assert rowcount == 3
        db_conn.commit()

        total = db_conn.execute("SELECT COUNT(*) FROM flight_positions").fetchone()[0]
        assert total == 3

    def test_duplicate_pk_ignored(self, db_conn: sqlite3.Connection) -> None:
        now = _now()
        insert_positions(db_conn, [("flight_A", now, 50.0, -104.0)])
        # Re-insert the exact same (flight_id, ts) — should not raise, not add row.
        rowcount = insert_positions(db_conn, [("flight_A", now, 51.0, -105.0)])
        # rowcount on conflicting INSERT OR IGNORE is implementation-defined;
        # what matters: total row count stays at 1, original lat/lon preserved.
        assert rowcount in (0, 1)
        rows = db_conn.execute(
            "SELECT lat, lon FROM flight_positions WHERE flight_id = 'flight_A'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["lat"] == pytest.approx(50.0)

    def test_empty_input(self, db_conn: sqlite3.Connection) -> None:
        assert insert_positions(db_conn, []) == 0


class TestFetchTrails:
    def test_returns_points_ordered_by_ts(self, db_conn: sqlite3.Connection) -> None:
        now = _now()
        # Insert out-of-order; expect ascending in result.
        insert_positions(
            db_conn,
            [
                ("flight_A", now + timedelta(seconds=10), 50.02, -104.02),
                ("flight_A", now, 50.0, -104.0),
                ("flight_A", now + timedelta(seconds=5), 50.01, -104.01),
            ],
        )
        db_conn.commit()

        trails = fetch_trails(db_conn, ["flight_A"])
        assert trails["flight_A"] == [
            [-104.0, 50.0],
            [-104.01, 50.01],
            [-104.02, 50.02],
        ]

    def test_cross_flight_isolation(self, db_conn: sqlite3.Connection) -> None:
        now = _now()
        insert_positions(
            db_conn,
            [
                ("flight_A", now, 50.0, -104.0),
                ("flight_B", now, 51.0, -105.0),
            ],
        )
        db_conn.commit()

        trails = fetch_trails(db_conn, ["flight_A", "flight_B"])
        assert trails["flight_A"] == [[-104.0, 50.0]]
        assert trails["flight_B"] == [[-105.0, 51.0]]

    def test_missing_flight_returns_empty_list(self, db_conn: sqlite3.Connection) -> None:
        trails = fetch_trails(db_conn, ["nonexistent"])
        assert trails == {"nonexistent": []}

    def test_empty_flight_id_list(self, db_conn: sqlite3.Connection) -> None:
        trails = fetch_trails(db_conn, [])
        assert trails == {}

    def test_coordinate_order_is_lon_lat(self, db_conn: sqlite3.Connection) -> None:
        # GeoJSON canonical order is [lon, lat] — not Leaflet's [lat, lon].
        # Test fixture lat=50, lon=-104 → result should be [-104, 50].
        insert_positions(db_conn, [("f1", _now(), 50.0, -104.0)])
        db_conn.commit()
        trails = fetch_trails(db_conn, ["f1"])
        assert trails["f1"][0] == [-104.0, 50.0]


class TestPruneOldPositions:
    def test_deletes_only_old_rows(self, db_conn: sqlite3.Connection) -> None:
        now = _now()
        insert_positions(
            db_conn,
            [
                ("flight_fresh", now - timedelta(minutes=10), 50.0, -104.0),
                ("flight_stale", now - timedelta(minutes=45), 50.0, -104.0),
            ],
        )
        db_conn.commit()

        deleted = prune_old_positions(db_conn, now=now, retention_minutes=30)
        assert deleted == 1
        remaining = {row[0] for row in db_conn.execute("SELECT flight_id FROM flight_positions")}
        assert remaining == {"flight_fresh"}

    def test_custom_retention_window(self, db_conn: sqlite3.Connection) -> None:
        now = _now()
        insert_positions(
            db_conn,
            [
                ("flight_old", now - timedelta(minutes=5), 50.0, -104.0),
                ("flight_new", now - timedelta(minutes=1), 50.0, -104.0),
            ],
        )
        db_conn.commit()

        # Aggressive: 2-minute retention. The 5-min row should go.
        deleted = prune_old_positions(db_conn, now=now, retention_minutes=2)
        assert deleted == 1
