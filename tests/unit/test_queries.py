"""Read-side queries — the 8 dashboard subcommands ported from sky-log-query.py.

Tests pin the result shape because dashboards bind to specific attribute
names. Changing a key name silently breaks the dashboard template until
the user notices a card showing 'unknown'.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.skywatch.models import Movement, Sighting
from custom_components.skywatch.storage import (
    insert_movement,
    insert_sighting,
    query_hour_histogram,
    query_military,
    query_movements_today,
    query_overhead,
    query_recent,
    query_search,
    query_stats,
    query_today,
    query_top_routes,
    query_watch_aircraft,
)

REGINA = ZoneInfo("America/Regina")


@pytest.fixture
def seeded(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    """A DB with a mix of sightings + movements for query tests."""
    base = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
    seedlings = [
        Sighting(
            exit_time=base,
            entry_time=base - timedelta(minutes=10),
            callsign="ACA123",
            flight_number="AC123",
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
        Sighting(
            exit_time=base - timedelta(hours=1),
            callsign="WJA456",
            airline="WestJet",
            airline_iata="WS",
            aircraft_code="B737",
            aircraft_model="Boeing 737-700",
            registration="C-GWSX",
            origin_iata="YYC",
            destination_iata="YVR",
            altitude_ft=8200,
            closest_km=4.2,  # Overhead (< 5km, < 10000ft)
        ),
        Sighting(
            exit_time=base - timedelta(days=2),
            callsign="RCH500",
            airline="USAF",
            aircraft_code="C17",
            aircraft_model="Boeing C-17 Globemaster III",
            registration="USAF7100",
            origin_iata="KSEA",
            destination_iata="CYWG",
            altitude_ft=34000,
            closest_km=18.0,
        ),
        Sighting(
            exit_time=base - timedelta(days=5),
            callsign="Blocked",
            aircraft_code="C182",
            aircraft_model="Cessna 182T Skylane",
            registration=None,
            altitude_ft=3500,
            closest_km=2.8,
        ),
        # Rare aircraft (seen once) — for stats query.
        Sighting(
            exit_time=base - timedelta(days=10),
            aircraft_code="LANC",
            aircraft_model="Lancair IV",
            registration="N777XX",
        ),
        # Aircraft seen twice (boundary case for the rare <=2 query).
        Sighting(
            exit_time=base - timedelta(days=11),
            aircraft_code="P3",
            aircraft_model="Lockheed P-3 Orion",
            registration="USN001",
        ),
        Sighting(
            exit_time=base - timedelta(days=12),
            aircraft_code="P3",
            aircraft_model="Lockheed P-3 Orion",
            registration="USN002",
        ),
    ]
    for s in seedlings:
        insert_sighting(db_conn, s)
    insert_movement(
        db_conn,
        Movement(
            event_time=base,
            direction="landed",
            airport_iata="YQR",
            callsign="WJA802",
            aircraft_code="B737",
        ),
    )
    insert_movement(
        db_conn,
        Movement(
            event_time=base - timedelta(minutes=30),
            direction="took_off",
            airport_iata="YQR",
            callsign="WJA803",
            aircraft_code="B737",
        ),
    )
    db_conn.commit()
    return db_conn


class TestRecent:
    def test_returns_paginated_shape(self, seeded: sqlite3.Connection) -> None:
        result = query_recent(seeded, page=1, tz=REGINA)
        assert set(result.keys()) >= {
            "count",
            "sightings",
            "page",
            "total_pages",
            "page_size",
            "total_count",
        }
        assert result["total_count"] == 7
        assert result["page_size"] == 10
        assert len(result["sightings"]) == 7

    def test_sighting_rows_are_decorated(self, seeded: sqlite3.Connection) -> None:
        rows = query_recent(seeded, page=1, tz=REGINA)["sightings"]
        first = rows[0]
        assert "exit_time_local" in first
        assert "dwell_seconds" in first
        assert "aircraft_info_url" in first
        assert first["aircraft_info_url"].startswith(
            "https://en.wikipedia.org/wiki/Special:Search?search="
        )

    def test_dwell_seconds_computed_when_entry_time_present(
        self, seeded: sqlite3.Connection
    ) -> None:
        rows = query_recent(seeded, page=1, tz=REGINA)["sightings"]
        with_dwell = [r for r in rows if r["dwell_seconds"] is not None]
        assert any(r["dwell_seconds"] == 600 for r in with_dwell)  # ACA123 entry-10min

    def test_dwell_seconds_none_when_no_entry_time(self, seeded: sqlite3.Connection) -> None:
        rows = query_recent(seeded, page=1, tz=REGINA)["sightings"]
        no_dwell = [r for r in rows if r["dwell_seconds"] is None]
        assert len(no_dwell) >= 1

    def test_page_clamps_to_total_pages(self, seeded: sqlite3.Connection) -> None:
        result = query_recent(seeded, page=999, tz=REGINA)
        assert result["page"] == result["total_pages"]


class TestSearch:
    def test_empty_term_returns_empty(self, seeded: sqlite3.Connection) -> None:
        result = query_search(seeded, term="", tz=REGINA)
        assert result == {"count": 0, "sightings": [], "term": ""}

    def test_match_by_callsign(self, seeded: sqlite3.Connection) -> None:
        result = query_search(seeded, term="ACA", tz=REGINA)
        assert result["count"] >= 1
        assert any("ACA" in (r.get("callsign") or "") for r in result["sightings"])

    def test_match_by_registration_case_insensitive(self, seeded: sqlite3.Connection) -> None:
        result = query_search(seeded, term="c-fgar", tz=REGINA)
        assert result["count"] == 1

    def test_match_by_iata(self, seeded: sqlite3.Connection) -> None:
        result = query_search(seeded, term="YYC", tz=REGINA)
        assert result["count"] >= 2


class TestStats:
    def test_total_matches_seedling_count(self, seeded: sqlite3.Connection) -> None:
        result = query_stats(seeded, tz=REGINA, now=datetime(2026, 6, 13, 23, 0, tzinfo=UTC))
        # 5 single-sighting models + 2 P-3 Orion rows = 7
        assert result["count"] == 7

    def test_top_airlines_present_and_sorted(self, seeded: sqlite3.Connection) -> None:
        result = query_stats(seeded, tz=REGINA)
        # Air Canada / WestJet / USAF each appear once → all show up.
        airlines = [r["airline"] for r in result["top_airlines"]]
        assert "Air Canada" in airlines

    def test_rare_aircraft_seen_twice_or_less(self, seeded: sqlite3.Connection) -> None:
        result = query_stats(seeded, tz=REGINA)
        rare = result["rare_aircraft"]
        models = [r["aircraft_model"] for r in rare]
        # Lancair IV: 1 sighting.
        assert "Lancair IV" in models
        # Lockheed P-3 Orion: 2 sightings — boundary of the rare query.
        assert "Lockheed P-3 Orion" in models
        # Verify the n counts on those entries.
        by_model = {r["aircraft_model"]: r["n"] for r in rare}
        assert by_model["Lancair IV"] == 1
        assert by_model["Lockheed P-3 Orion"] == 2

    def test_rare_aircraft_orders_singletons_first(self, seeded: sqlite3.Connection) -> None:
        result = query_stats(seeded, tz=REGINA)
        rare = result["rare_aircraft"]
        # The query orders by n ASC then last_seen DESC, so every n=1
        # row appears before any n=2 row.
        last_n1_index = max((i for i, r in enumerate(rare) if r["n"] == 1), default=-1)
        first_n2_index = min((i for i, r in enumerate(rare) if r["n"] == 2), default=len(rare))
        assert last_n1_index < first_n2_index


class TestTopRoutes:
    def test_groups_by_origin_destination(self, seeded: sqlite3.Connection) -> None:
        result = query_top_routes(seeded)
        routes = {(r["origin_iata"], r["destination_iata"]): r["n"] for r in result["routes"]}
        assert routes[("YYC", "YVR")] == 2


class TestOverhead:
    def test_filters_by_threshold(self, seeded: sqlite3.Connection) -> None:
        result = query_overhead(seeded, distance_km=5.0, altitude_ft=10000)
        # WJA456 (4.2 km, 8200 ft) and the Cessna 182T (2.8 km, 3500 ft) qualify.
        # ACA123 is at 10500 ft → exceeds altitude_ft.
        assert result["count"] == 2

    def test_threshold_overrides_take_effect(self, seeded: sqlite3.Connection) -> None:
        # Loosen altitude to include ACA123 at 10500ft.
        result = query_overhead(seeded, distance_km=5.0, altitude_ft=11000)
        assert result["count"] == 3


class TestMilitary:
    def test_matches_codes_case_insensitive(self, seeded: sqlite3.Connection) -> None:
        result = query_military(seeded, codes=("C17",), tz=REGINA)
        assert result["count"] == 1
        assert result["sightings"][0]["aircraft_code"] == "C17"

    def test_empty_codes_returns_zero(self, seeded: sqlite3.Connection) -> None:
        result = query_military(seeded, codes=(), tz=REGINA)
        assert result == {"count": 0, "sightings": []}

    def test_multiple_codes(self, seeded: sqlite3.Connection) -> None:
        result = query_military(seeded, codes=("C17", "C130", "P8"), tz=REGINA)
        assert result["count"] == 1  # only C17 in seed


class TestWatchAircraft:
    def test_match_by_registration(self, seeded: sqlite3.Connection) -> None:
        result = query_watch_aircraft(seeded, registration="C-FGAR", tz=REGINA)
        assert result["count"] == 1
        assert result["last_callsign"] == "ACA123"

    def test_fingerprint_match_for_blocked(self, seeded: sqlite3.Connection) -> None:
        # C182 + callsign='Blocked' + null reg should match via fingerprint.
        result = query_watch_aircraft(
            seeded, registration="C-GRPF", tz=REGINA, fingerprint_code="C182"
        )
        assert result["count"] == 1
        assert result["last_aircraft_model"] == "Cessna 182T Skylane"

    def test_no_fingerprint_misses_blocked(self, seeded: sqlite3.Connection) -> None:
        result = query_watch_aircraft(seeded, registration="C-GRPF", tz=REGINA)
        assert result["count"] == 0

    def test_fingerprint_only_match_no_registration(self, seeded: sqlite3.Connection) -> None:
        # Watch with no registration but only a fingerprint — matches
        # the Blocked + null-reg + C182 row.
        result = query_watch_aircraft(seeded, registration="", tz=REGINA, fingerprint_code="C182")
        assert result["count"] == 1

    def test_empty_reg_and_no_fingerprint_returns_zero(self, seeded: sqlite3.Connection) -> None:
        result = query_watch_aircraft(seeded, registration="", tz=REGINA)
        assert result["count"] == 0

    def test_relative_time_format(self, seeded: sqlite3.Connection) -> None:
        now = datetime(2026, 6, 13, 12, 30, 0, tzinfo=UTC)  # 30 minutes after base
        result = query_watch_aircraft(seeded, registration="C-FGAR", tz=REGINA, now=now)
        assert result["last_seen_relative"] == "30 min ago"


class TestMovementsToday:
    def test_returns_landed_and_took_off_counts(self, seeded: sqlite3.Connection) -> None:
        # 'now' chosen so the seedling base (2026-06-13 12:00 UTC, = 06:00 local
        # America/Regina UTC-6) is "today" in local tz.
        now = datetime(2026, 6, 13, 23, 0, tzinfo=UTC)
        result = query_movements_today(seeded, tz=REGINA, now=now)
        assert result["landed"] == 1
        assert result["took_off"] == 1
        assert result["count"] == 2


class TestToday:
    def test_count_only(self, seeded: sqlite3.Connection) -> None:
        now = datetime(2026, 6, 13, 23, 0, tzinfo=UTC)
        result = query_today(seeded, tz=REGINA, now=now)
        # ACA123 (base 12:00 UTC = 06:00 local) and WJA456 (base-1h = 11:00 UTC
        # = 05:00 local) are both today (after local midnight at 06:00 UTC).
        assert result["count"] == 2


class TestHourHistogram:
    def test_24_buckets(self, seeded: sqlite3.Connection) -> None:
        result = query_hour_histogram(seeded, tz=REGINA)
        assert len(result["buckets"]) == 24
        # Sum of bucket counts equals total sightings.
        assert sum(b["n"] for b in result["buckets"]) == 7

    def test_max_n_is_largest_bucket(self, seeded: sqlite3.Connection) -> None:
        result = query_hour_histogram(seeded, tz=REGINA)
        assert result["max_n"] == max(b["n"] for b in result["buckets"])
