"""SerializedConnection — concurrent units of work on one shared connection.

The coordinator dispatches every DB call through HA's executor, a thread
pool, so exits, entries, movements, trail captures and refresh reads run
concurrently against one sqlite3.Connection. Without serialization the
threads interleave inside each other's transactions and sightings are
lost ("cannot commit - no transaction is active", "bad parameter or other
API misuse"). These tests hammer the real units of work from many threads.
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.skywatch.data_builder import build_data
from custom_components.skywatch.models import Entry, Movement, Sighting
from custom_components.skywatch.storage import (
    SerializedConnection,
    open_db,
    record_entry,
    record_exit,
    record_movement,
    record_positions,
)

FLIGHTS = 100
# Recent, so prune_stale_entries (TTL from now) keeps the entries rows.
T0 = datetime.now(UTC).replace(microsecond=0)


def _read(conn: sqlite3.Connection) -> dict:
    return build_data(
        conn,
        tz=ZoneInfo("America/Regina"),
        current_page=1,
        current_search="",
        military_codes=(),
        watch_list=(),
    )


def _hammer(db: SerializedConnection) -> list[BaseException]:
    """Fire every kind of unit concurrently; return any exceptions raised."""
    # Durability is not under test; skip fsync so ~500 commits stay fast on
    # slow CI disks.
    db.run(lambda conn: conn.execute("PRAGMA synchronous = OFF"))
    for i in range(FLIGHTS):
        db.run(record_entry, Entry(flight_id=f"f{i}", entry_time=T0, callsign=f"CS{i}"))

    jobs = []
    for i in range(FLIGHTS):
        jobs.append(
            (
                record_exit,
                f"f{i}",
                Sighting(exit_time=T0 + timedelta(minutes=5), callsign=f"CS{i}"),
            )
        )
        jobs.append((record_movement, Movement(event_time=T0, direction="landed")))
        jobs.append((record_positions, [(f"f{i}", datetime.now(UTC), 50.4, -104.6)]))
        jobs.append((_read,))

    errors: list[BaseException] = []
    start = threading.Barrier(16)

    def worker(job: tuple) -> None:
        with contextlib.suppress(threading.BrokenBarrierError):
            start.wait(timeout=0.5)
        try:
            db.run(*job)
        except BaseException as err:  # collected for the assertion
            errors.append(err)

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(worker, jobs))
    return errors


def test_concurrent_units_of_work_lose_nothing(db_path: Path) -> None:
    db = SerializedConnection(open_db(db_path))
    try:
        errors = _hammer(db)
        assert errors == []

        def counts(conn: sqlite3.Connection) -> tuple[int, int, int, int]:
            return conn.execute(
                "SELECT (SELECT COUNT(*) FROM sightings),"
                " (SELECT COUNT(*) FROM sightings WHERE entry_time IS NOT NULL),"
                " (SELECT COUNT(*) FROM airport_movements),"
                " (SELECT COUNT(*) FROM entries)"
            ).fetchone()

        sightings, joined, movements, entries_left = db.run(counts)
        assert sightings == FLIGHTS
        assert joined == FLIGHTS  # every exit found its entry row
        assert movements == FLIGHTS
        assert entries_left == 0
        assert not db.run(lambda conn: conn.in_transaction)
    finally:
        db.close()


def test_failed_unit_does_not_leak_its_transaction(db_path: Path) -> None:
    """A unit that raises mid-transaction is rolled back, so the next
    caller's commit can't persist half of it."""
    db = SerializedConnection(open_db(db_path))
    try:

        def half_written(conn: sqlite3.Connection) -> None:
            conn.execute("INSERT INTO sightings(exit_time, callsign) VALUES('x', 'HALF')")
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            db.run(half_written)
        db.run(record_movement, Movement(event_time=T0, direction="landed"))

        assert (
            db.run(
                lambda conn: conn.execute(
                    "SELECT COUNT(*) FROM sightings WHERE callsign = 'HALF'"
                ).fetchone()[0]
            )
            == 0
        )
    finally:
        db.close()


def test_run_after_close_raises(db_path: Path) -> None:
    db = SerializedConnection(open_db(db_path))
    db.close()
    db.close()  # idempotent
    assert db.closed
    with pytest.raises(sqlite3.ProgrammingError):
        db.run(_read)
