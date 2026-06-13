"""Data builder — assembles the coordinator's per-tick data dict.

Pure function: takes a sqlite3 connection + config and returns a dict.
No HA imports, no scheduling, no event loop. Trivially testable against
a tmp_path SQLite seeded with sightings.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.skywatch.classify import WatchEntry
from custom_components.skywatch.const import DEFAULT_MILITARY_CODES
from custom_components.skywatch.data_builder import build_data
from custom_components.skywatch.models import Sighting
from custom_components.skywatch.storage import insert_sighting

REGINA = ZoneInfo("America/Regina")


@pytest.fixture
def seeded(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    base = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
    insert_sighting(
        db_conn,
        Sighting(
            exit_time=base,
            callsign="ACA123",
            airline="Air Canada",
            airline_iata="AC",
            aircraft_code="B738",
            aircraft_model="Boeing 737-800",
            registration="C-FGAR",
            origin_iata="YYC",
            destination_iata="YVR",
            altitude_ft=10500,
            closest_km=3.5,
        ),
    )
    insert_sighting(
        db_conn,
        Sighting(
            exit_time=base - timedelta(days=2),
            callsign="RCH500",
            aircraft_code="C17",
            aircraft_model="Boeing C-17",
            altitude_ft=34000,
            closest_km=18.0,
        ),
    )
    # Blocked C182 (matching Regina Police fingerprint).
    insert_sighting(
        db_conn,
        Sighting(
            exit_time=base - timedelta(days=5),
            callsign="Blocked",
            aircraft_code="C182",
            aircraft_model="Cessna 182T",
            registration=None,
            altitude_ft=3500,
            closest_km=2.8,
        ),
    )
    db_conn.commit()
    return db_conn


def test_data_dict_has_all_top_level_keys(seeded: sqlite3.Connection) -> None:
    data = build_data(
        seeded,
        tz=REGINA,
        current_page=1,
        current_search="",
        military_codes=DEFAULT_MILITARY_CODES,
        watch_list=(),
    )
    expected_keys = {
        "today",
        "stats",
        "recent",
        "overhead",
        "military",
        "top_routes",
        "hour_histogram",
        "movements_today",
        "search",
        "watches",
    }
    assert expected_keys.issubset(set(data.keys()))


def test_search_is_empty_shape_when_term_blank(
    seeded: sqlite3.Connection,
) -> None:
    data = build_data(
        seeded,
        tz=REGINA,
        current_page=1,
        current_search="",
        military_codes=DEFAULT_MILITARY_CODES,
        watch_list=(),
    )
    assert data["search"] == {"count": 0, "sightings": [], "term": ""}


def test_search_populated_when_term_present(seeded: sqlite3.Connection) -> None:
    data = build_data(
        seeded,
        tz=REGINA,
        current_page=1,
        current_search="ACA",
        military_codes=DEFAULT_MILITARY_CODES,
        watch_list=(),
    )
    assert data["search"]["term"] == "ACA"
    assert data["search"]["count"] >= 1


def test_watches_keyed_by_slug(seeded: sqlite3.Connection) -> None:
    watch_list = (
        WatchEntry(
            slug="regina_police",
            label="Regina Police",
            aircraft_code="C182",
            match_blocked=True,
        ),
        WatchEntry(slug="aca123_jet", label="ACA123", registration="C-FGAR"),
    )
    data = build_data(
        seeded,
        tz=REGINA,
        current_page=1,
        current_search="",
        military_codes=DEFAULT_MILITARY_CODES,
        watch_list=watch_list,
    )
    assert set(data["watches"].keys()) == {"regina_police", "aca123_jet"}
    # Blocked C-GRPF fingerprint should find the seeded Blocked C182 sighting.
    assert data["watches"]["regina_police"]["count"] == 1
    assert data["watches"]["aca123_jet"]["count"] == 1


def test_military_query_uses_supplied_codes(seeded: sqlite3.Connection) -> None:
    data = build_data(
        seeded,
        tz=REGINA,
        current_page=1,
        current_search="",
        military_codes=("C17",),
        watch_list=(),
    )
    # Only C17 in the seeded military codes — the seeded C-17 row qualifies.
    assert data["military"]["count"] == 1


def test_overhead_thresholds_configurable(seeded: sqlite3.Connection) -> None:
    # Tight (only the 3500ft / 2.8km C182).
    tight = build_data(
        seeded,
        tz=REGINA,
        current_page=1,
        current_search="",
        military_codes=DEFAULT_MILITARY_CODES,
        watch_list=(),
        overhead_distance_km=5.0,
        overhead_altitude_ft=10000,
    )
    # Loose (also the 10500ft ACA123).
    loose = build_data(
        seeded,
        tz=REGINA,
        current_page=1,
        current_search="",
        military_codes=DEFAULT_MILITARY_CODES,
        watch_list=(),
        overhead_distance_km=5.0,
        overhead_altitude_ft=11000,
    )
    assert loose["overhead"]["count"] > tight["overhead"]["count"]
