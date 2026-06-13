"""Read-side data access — the 8 dashboard queries.

Ported from sky-log-query.py. Every read function returns a dict in the
shape the existing dashboard YAML expects — backward compatibility with
the ha-tinker dashboards is a non-goal-for-cleanliness but a hard goal
for migration UX. Skywatch is meant to be a drop-in replacement, not a
re-architecture that forces users to rewrite their dashboards.

All "local time" calculations take an explicit ZoneInfo so the queries
are timezone-independent. The legacy script hardcoded America/Regina —
that's now the caller's responsibility to pass in.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

DEFAULT_RECENT_PAGE_SIZE = 10
DEFAULT_SEARCH_LIMIT = 25
DEFAULT_OVERHEAD_LIMIT = 50
DEFAULT_MILITARY_LIMIT = 50
DEFAULT_MOVEMENTS_LIMIT = 30
DEFAULT_AIRCRAFT_RECENT_LIMIT = 10

WIKI_SEARCH = "https://en.wikipedia.org/wiki/Special:Search?search="


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _decorate(rows: Iterable[sqlite3.Row], tz: ZoneInfo) -> list[dict]:
    """Add exit_time_local / dwell_seconds / aircraft_info_url to every row.

    dashboard-sky binds to these decorated fields, so we add them at the
    repository boundary rather than make the dashboard YAML compute them.
    """
    out: list[dict] = []
    for raw in rows:
        row = dict(raw)
        exit_dt = _parse_iso(row.get("exit_time"))
        row["exit_time_local"] = (
            exit_dt.astimezone(tz).strftime("%Y-%m-%d %H:%M") if exit_dt else None
        )
        entry_dt = _parse_iso(row.get("entry_time"))
        if exit_dt and entry_dt:
            row["dwell_seconds"] = int((exit_dt - entry_dt).total_seconds())
        else:
            row["dwell_seconds"] = None
        search_text = row.get("aircraft_model") or row.get("aircraft_code")
        row["aircraft_info_url"] = WIKI_SEARCH + quote_plus(search_text) if search_text else None
        out.append(row)
    return out


def _local_midnight_utc_iso(tz: ZoneInfo, now: datetime | None = None) -> str:
    now = datetime.now(tz) if now is None else now.astimezone(tz)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(UTC).isoformat(timespec="seconds")


def query_recent(
    conn: sqlite3.Connection,
    page: int,
    tz: ZoneInfo,
    page_size: int = DEFAULT_RECENT_PAGE_SIZE,
) -> dict:
    page = max(1, int(page))
    total = int(conn.execute("SELECT COUNT(*) FROM sightings").fetchone()[0])
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    offset = (page - 1) * page_size
    cur = conn.execute(
        "SELECT * FROM sightings ORDER BY exit_time DESC LIMIT ? OFFSET ?",
        (page_size, offset),
    )
    rows = _decorate(cur.fetchall(), tz)
    return {
        "count": len(rows),
        "sightings": rows,
        "page": page,
        "total_pages": total_pages,
        "page_size": page_size,
        "total_count": total,
    }


def query_today(conn: sqlite3.Connection, tz: ZoneInfo, now: datetime | None = None) -> dict:
    cutoff = _local_midnight_utc_iso(tz, now)
    count = int(
        conn.execute("SELECT COUNT(*) FROM sightings WHERE exit_time >= ?", (cutoff,)).fetchone()[0]
    )
    return {"count": count}


def query_search(
    conn: sqlite3.Connection,
    term: str,
    tz: ZoneInfo,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> dict:
    term = (term or "").strip()
    if not term:
        return {"count": 0, "sightings": [], "term": ""}
    needle = f"%{term.upper()}%"
    cur = conn.execute(
        """SELECT * FROM sightings
           WHERE UPPER(IFNULL(callsign,'')) LIKE ?
              OR UPPER(IFNULL(flight_number,'')) LIKE ?
              OR UPPER(IFNULL(airline,'')) LIKE ?
              OR UPPER(IFNULL(airline_iata,'')) LIKE ?
              OR UPPER(IFNULL(registration,'')) LIKE ?
              OR UPPER(IFNULL(origin_iata,'')) LIKE ?
              OR UPPER(IFNULL(destination_iata,'')) LIKE ?
              OR UPPER(IFNULL(aircraft_code,'')) LIKE ?
              OR UPPER(IFNULL(aircraft_model,'')) LIKE ?
           ORDER BY exit_time DESC LIMIT ?""",
        (needle, needle, needle, needle, needle, needle, needle, needle, needle, limit),
    )
    rows = _decorate(cur.fetchall(), tz)
    return {"count": len(rows), "sightings": rows, "term": term}


def query_stats(conn: sqlite3.Connection, tz: ZoneInfo, now: datetime | None = None) -> dict:
    total = int(conn.execute("SELECT COUNT(*) FROM sightings").fetchone()[0])
    cutoff = _local_midnight_utc_iso(tz, now)
    today = int(
        conn.execute("SELECT COUNT(*) FROM sightings WHERE exit_time >= ?", (cutoff,)).fetchone()[0]
    )
    week = int(
        conn.execute(
            "SELECT COUNT(*) FROM sightings WHERE exit_time >= datetime('now','-7 days')"
        ).fetchone()[0]
    )
    airlines = [
        dict(r)
        for r in conn.execute(
            """SELECT airline, COUNT(*) AS n FROM sightings
               WHERE airline IS NOT NULL AND airline <> ''
               GROUP BY airline ORDER BY n DESC LIMIT 10"""
        )
    ]
    aircraft = [
        dict(r)
        for r in conn.execute(
            """SELECT aircraft_model, COUNT(*) AS n FROM sightings
               WHERE aircraft_model IS NOT NULL AND aircraft_model <> ''
               GROUP BY aircraft_model ORDER BY n DESC LIMIT 10"""
        )
    ]
    rare = [
        dict(r)
        for r in conn.execute(
            """SELECT aircraft_model, COUNT(*) AS n, MAX(exit_time) AS last_seen
               FROM sightings
               WHERE aircraft_model IS NOT NULL AND aircraft_model <> ''
               GROUP BY aircraft_model
               HAVING n = 1
               ORDER BY last_seen DESC LIMIT 10"""
        )
    ]
    return {
        "count": total,
        "today": today,
        "this_week": week,
        "top_airlines": airlines,
        "top_aircraft": aircraft,
        "rare_aircraft": rare,
    }


def query_top_routes(conn: sqlite3.Connection) -> dict:
    rows = [
        dict(r)
        for r in conn.execute(
            """SELECT origin_iata, destination_iata, COUNT(*) AS n
               FROM sightings
               WHERE origin_iata IS NOT NULL AND destination_iata IS NOT NULL
                 AND origin_iata != '' AND destination_iata != ''
               GROUP BY origin_iata, destination_iata
               ORDER BY n DESC LIMIT 10"""
        )
    ]
    return {"count": len(rows), "routes": rows}


def query_overhead(
    conn: sqlite3.Connection,
    distance_km: float = 5.0,
    altitude_ft: int = 10000,
    limit: int = DEFAULT_OVERHEAD_LIMIT,
) -> dict:
    total = int(
        conn.execute(
            "SELECT COUNT(*) FROM sightings WHERE closest_km < ? AND altitude_ft < ?",
            (distance_km, altitude_ft),
        ).fetchone()[0]
    )
    rows = [
        dict(r)
        for r in conn.execute(
            """SELECT exit_time, callsign, flight_number, airline,
                      aircraft_model, origin_iata, destination_iata,
                      altitude_ft, closest_km, aircraft_photo
               FROM sightings
               WHERE closest_km < ? AND altitude_ft < ?
               ORDER BY exit_time DESC
               LIMIT ?""",
            (distance_km, altitude_ft, limit),
        )
    ]
    return {"count": total, "recent_overhead": rows}


def query_military(
    conn: sqlite3.Connection,
    codes: tuple[str, ...],
    tz: ZoneInfo,
    limit: int = DEFAULT_MILITARY_LIMIT,
) -> dict:
    if not codes:
        return {"count": 0, "sightings": []}
    placeholders = ",".join(["?"] * len(codes))
    rows = _decorate(
        conn.execute(
            f"""SELECT * FROM sightings
                WHERE UPPER(IFNULL(aircraft_code,'')) IN ({placeholders})
                ORDER BY exit_time DESC LIMIT ?""",
            (*codes, limit),
        ).fetchall(),
        tz,
    )
    total = int(
        conn.execute(
            f"""SELECT COUNT(*) FROM sightings
                WHERE UPPER(IFNULL(aircraft_code,'')) IN ({placeholders})""",
            codes,
        ).fetchone()[0]
    )
    return {"count": total, "sightings": rows}


def query_hour_histogram(conn: sqlite3.Connection, tz: ZoneInfo) -> dict:
    """24-hour bucket counts in the configured local tz.

    The legacy SQL hardcoded '-6 hours' (America/Regina, no DST). For a
    portable integration we must compute the bucket Python-side so users
    in DST-observing zones get correct counts in fall/spring.
    """
    counts = [0] * 24
    for raw in conn.execute("SELECT exit_time FROM sightings WHERE exit_time IS NOT NULL"):
        dt = _parse_iso(raw[0])
        if dt is None:
            continue
        counts[dt.astimezone(tz).hour] += 1
    buckets = [{"hour": h, "n": counts[h]} for h in range(24)]
    max_n = max(counts) if counts else 0
    return {"count": sum(counts), "max_n": max_n, "buckets": buckets}


def query_movements_today(
    conn: sqlite3.Connection,
    tz: ZoneInfo,
    now: datetime | None = None,
    limit: int = DEFAULT_MOVEMENTS_LIMIT,
) -> dict:
    cutoff = _local_midnight_utc_iso(tz, now)
    rows = [
        dict(r)
        for r in conn.execute(
            """SELECT event_time, direction, callsign, flight_number,
                      airline_iata, aircraft_code, aircraft_model,
                      origin_iata, destination_iata
               FROM airport_movements
               WHERE event_time >= ?
               ORDER BY event_time DESC LIMIT ?""",
            (cutoff, limit),
        )
    ]
    landed = 0
    took_off = 0
    for row in rows:
        dt = _parse_iso(row.get("event_time"))
        row["event_time_local"] = dt.astimezone(tz).strftime("%H:%M") if dt else None
        if row.get("direction") == "landed":
            landed += 1
        elif row.get("direction") == "took_off":
            took_off += 1
    return {
        "count": len(rows),
        "landed": landed,
        "took_off": took_off,
        "movements": rows,
    }


def query_watch_aircraft(
    conn: sqlite3.Connection,
    registration: str,
    tz: ZoneInfo,
    fingerprint_code: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Per-aircraft watch query.

    Matches by uppercase registration, OR — when fingerprint_code is given
    — by (aircraft_code = fingerprint AND callsign = 'Blocked' AND
    registration IS NULL). This is the FR24 privacy-block escape: when an
    airframe's registration is suppressed at the source, we identify it
    by its fingerprint (the canonical case is Regina Police Air Unit
    C-GRPF, a Cessna 182T that shows up as 'Blocked' with no registration).
    """
    reg = (registration or "").strip().upper()
    fp = (fingerprint_code or "").strip().upper()
    if not reg:
        return {"count": 0, "registration": "", "last_seen": None, "recent": []}
    if fp:
        where = (
            "UPPER(IFNULL(registration,'')) = ? "
            "OR (UPPER(IFNULL(aircraft_code,'')) = ? "
            "    AND callsign = 'Blocked' "
            "    AND registration IS NULL)"
        )
        params: tuple = (reg, fp)
    else:
        where = "UPPER(IFNULL(registration,'')) = ?"
        params = (reg,)
    total = int(conn.execute(f"SELECT COUNT(*) FROM sightings WHERE {where}", params).fetchone()[0])
    recent = _decorate(
        conn.execute(
            f"SELECT * FROM sightings WHERE {where} "
            f"ORDER BY exit_time DESC LIMIT {DEFAULT_AIRCRAFT_RECENT_LIMIT}",
            params,
        ).fetchall(),
        tz,
    )
    last = recent[0] if recent else {}
    last_seen = last.get("exit_time")
    relative = None
    if last_seen:
        dt = _parse_iso(last_seen)
        if dt:
            anchor = (now or datetime.now(UTC)).astimezone(UTC)
            seconds = int((anchor - dt).total_seconds())
            if seconds < 60:
                relative = "just now"
            elif seconds < 3600:
                relative = f"{seconds // 60} min ago"
            elif seconds < 86400:
                relative = f"{seconds // 3600} h ago"
            else:
                relative = f"{seconds // 86400} days ago"
    return {
        "count": total,
        "registration": reg,
        "last_seen": last_seen,
        "last_seen_local": last.get("exit_time_local"),
        "last_seen_relative": relative,
        "last_callsign": last.get("callsign"),
        "last_flight_number": last.get("flight_number"),
        "last_origin": last.get("origin_iata"),
        "last_destination": last.get("destination_iata"),
        "last_altitude_ft": last.get("altitude_ft"),
        "last_closest_km": last.get("closest_km"),
        "last_aircraft_model": last.get("aircraft_model"),
        "recent": recent[:5],
    }
