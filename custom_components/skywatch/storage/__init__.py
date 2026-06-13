"""Skywatch storage layer.

Public surface — coordinator imports go through here.
"""

from __future__ import annotations

from .connection import open_db
from .migrations import run_migrations
from .normalizers import coerce_float, coerce_int, normalize_photo_url, parse_iso
from .queries import (
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
from .repository import (
    fetch_trails,
    insert_entry,
    insert_movement,
    insert_positions,
    insert_sighting,
    prune_old_positions,
    prune_stale_entries,
    take_entry_time,
)
from .schema import SCHEMA_VERSION

__all__ = [
    "SCHEMA_VERSION",
    "coerce_float",
    "coerce_int",
    "fetch_trails",
    "insert_entry",
    "insert_movement",
    "insert_positions",
    "insert_sighting",
    "normalize_photo_url",
    "open_db",
    "parse_iso",
    "prune_old_positions",
    "prune_stale_entries",
    "query_active_1h",
    "query_active_24h",
    "query_hour_histogram",
    "query_military",
    "query_movements_today",
    "query_overhead",
    "query_recent",
    "query_search",
    "query_stats",
    "query_today",
    "query_top_routes",
    "query_watch_aircraft",
    "run_migrations",
    "take_entry_time",
]
