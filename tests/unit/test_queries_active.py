"""query_active_1h / query_active_24h rolling-window counts."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.skywatch.models import Sighting
from custom_components.skywatch.storage import (
    insert_sighting,
    query_active_1h,
    query_active_24h,
)


@pytest.fixture
def db_with_rolling_data(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    """4 sightings: 5 min ago, 30 min ago, 5 h ago, 2 days ago."""
    now = datetime(2026, 6, 13, 20, 0, 0, tzinfo=UTC)
    rows = [
        (now - timedelta(minutes=5), "FRESH"),
        (now - timedelta(minutes=30), "WITHIN1H"),
        (now - timedelta(hours=5), "WITHIN24H"),
        (now - timedelta(days=2), "OLD"),
    ]
    for exit_time, callsign in rows:
        insert_sighting(db_conn, Sighting(exit_time=exit_time, callsign=callsign))
    db_conn.commit()
    return db_conn


def test_active_1h_includes_only_last_hour(
    db_with_rolling_data: sqlite3.Connection,
) -> None:
    now = datetime(2026, 6, 13, 20, 0, 0, tzinfo=UTC)
    result = query_active_1h(db_with_rolling_data, now=now)
    # Only the 5-min and 30-min rows qualify.
    assert result == {"count": 2}


def test_active_24h_includes_last_day(
    db_with_rolling_data: sqlite3.Connection,
) -> None:
    now = datetime(2026, 6, 13, 20, 0, 0, tzinfo=UTC)
    result = query_active_24h(db_with_rolling_data, now=now)
    # 5-min, 30-min, 5-h qualify (3); the 2-day row does not.
    assert result == {"count": 3}


def test_active_1h_zero_on_empty_db(db_conn: sqlite3.Connection) -> None:
    result = query_active_1h(db_conn, now=datetime(2026, 6, 13, 20, 0, 0, tzinfo=UTC))
    assert result == {"count": 0}


def test_active_24h_zero_on_empty_db(db_conn: sqlite3.Connection) -> None:
    result = query_active_24h(db_conn, now=datetime(2026, 6, 13, 20, 0, 0, tzinfo=UTC))
    assert result == {"count": 0}


def test_active_1h_uses_real_now_when_not_provided(
    db_conn: sqlite3.Connection,
) -> None:
    # Seed data at 2020-01-01 — definitively in the past relative to real
    # 'now', so the default-arg path (datetime.now(UTC) inside the query)
    # filters them all out.
    ancient = datetime(2020, 1, 1, 12, 0, 0, tzinfo=UTC)
    insert_sighting(db_conn, Sighting(exit_time=ancient, callsign="ANCIENT"))
    db_conn.commit()

    result = query_active_1h(db_conn)
    assert result["count"] == 0
