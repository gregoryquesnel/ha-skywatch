"""Pure-function data builder for the coordinator.

Runs all 9 dashboard queries against a sqlite3 connection and assembles
the data dict the platforms consume. No HA imports — tests can build
the dict from a tmp_path DB and assert the shape directly.

The coordinator wraps this in `hass.async_add_executor_job` so SQLite
work stays off the event loop.
"""

from __future__ import annotations

import sqlite3
from zoneinfo import ZoneInfo

from .classify import WatchEntry
from .storage import (
    query_active_1h,
    query_active_24h,
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


def build_data(
    conn: sqlite3.Connection,
    *,
    tz: ZoneInfo,
    current_page: int,
    current_search: str,
    military_codes: tuple[str, ...],
    watch_list: tuple[WatchEntry, ...],
    overhead_distance_km: float = 5.0,
    overhead_altitude_ft: int = 10000,
    currently_in_area_count: int = 0,
) -> dict:
    """Build the coordinator's data dict for a single refresh tick.

    Returns a dict keyed by query name (recent, today, stats, etc.). The
    `watches` key holds a sub-dict keyed by watch-entry slug, each value
    being a `query_watch_aircraft` result.
    """
    data: dict = {
        "today": query_today(conn, tz),
        "stats": query_stats(conn, tz),
        "recent": query_recent(conn, current_page, tz),
        "overhead": query_overhead(
            conn,
            distance_km=overhead_distance_km,
            altitude_ft=overhead_altitude_ft,
        ),
        "military": query_military(conn, military_codes, tz),
        "top_routes": query_top_routes(conn),
        "hour_histogram": query_hour_histogram(conn, tz),
        "movements_today": query_movements_today(conn, tz),
        # 'active in last N hours' = completed transits in window + aircraft
        # currently in area. The two sets are disjoint (a flight that's
        # currently in area hasn't generated a sighting row yet), so the
        # sum is the distinct count of aircraft with area presence during
        # the window. Without the currently-in-area term, a plane that
        # entered 30 min ago and is still visible doesn't get counted —
        # which is the bug the user hit ('active last 1h = 0' even though
        # multiple planes were obviously in view).
        "active_1h": {"count": query_active_1h(conn)["count"] + currently_in_area_count},
        "active_24h": {"count": query_active_24h(conn)["count"] + currently_in_area_count},
    }
    if current_search:
        data["search"] = query_search(conn, current_search, tz)
    else:
        data["search"] = {"count": 0, "sightings": [], "term": ""}

    watches: dict[str, dict] = {}
    for entry in watch_list:
        watches[entry.slug] = query_watch_aircraft(
            conn,
            registration=entry.registration or "",
            tz=tz,
            fingerprint_code=entry.aircraft_code if entry.match_blocked else None,
        )
    data["watches"] = watches
    return data
