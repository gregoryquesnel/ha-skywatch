"""Skywatch storage layer.

Public surface — coordinator imports go through here.
"""

from __future__ import annotations

from .connection import open_db
from .migrations import run_migrations
from .normalizers import coerce_float, coerce_int, normalize_photo_url, parse_iso
from .queries import (
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
    insert_entry,
    insert_movement,
    insert_sighting,
    prune_stale_entries,
    take_entry_time,
)
from .schema import SCHEMA_VERSION

__all__ = [
    "SCHEMA_VERSION",
    "coerce_float",
    "coerce_int",
    "insert_entry",
    "insert_movement",
    "insert_sighting",
    "normalize_photo_url",
    "open_db",
    "parse_iso",
    "prune_stale_entries",
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
