#!/usr/bin/env python3
"""Backfill a time window from a legacy sky_sightings.db into a live skywatch DB.

Thin CLI around custom_components/skywatch/legacy_import.py:import_legacy_window,
loaded by file path so it runs on the HA host with the stock python3 and no
Home Assistant imports, and without a Core restart (the running integration
keeps its own connection open; SQLite WAL locking arbitrates).

Typical use, on the HA host:

    sudo python3 backfill-legacy-window.py \
        --module /config/custom_components/skywatch/legacy_import.py \
        --since 2026-06-13T12:02:07+00:00 --until 2026-10-10T20:22:58+00:00 \
        --dry-run

then re-run without --dry-run, plus --backup <path> to take an online
(sqlite3 backup API) snapshot of the target first. Re-running is safe:
rows already present in the target are skipped (see legacy_import.py for
the identity rule).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

DEFAULT_MODULE = Path(__file__).resolve().parent.parent / (
    "custom_components/skywatch/legacy_import.py"
)


def _load_legacy_import(path: Path):
    spec = importlib.util.spec_from_file_location("skywatch_legacy_import", path)
    if spec is None or spec.loader is None:
        sys.exit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "import_legacy_window"):
        sys.exit(f"{path} has no import_legacy_window — use a skywatch build that ships it")
    return module


def _online_backup(src: Path, dest: Path, busy_timeout_ms: int) -> None:
    if dest.exists():
        sys.exit(f"backup target {dest} already exists — refusing to overwrite")
    s = sqlite3.connect(src, timeout=busy_timeout_ms / 1000)
    d = sqlite3.connect(dest)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()
    check = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    if result != "ok":
        sys.exit(f"backup {dest} failed integrity_check: {result}")
    print(f"backup: {dest} (integrity_check ok)")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--target", type=Path, default=Path("/config/skywatch/sightings.db"))
    p.add_argument("--source", type=Path, default=Path("/config/sky_sightings.db"))
    p.add_argument("--module", type=Path, default=DEFAULT_MODULE)
    p.add_argument("--since", help="inclusive lower bound, ISO 8601 (naive = UTC)")
    p.add_argument("--until", help="exclusive upper bound, ISO 8601 (naive = UTC)")
    p.add_argument("--tolerance-seconds", type=int, default=None)
    p.add_argument("--busy-timeout-ms", type=int, default=30000)
    p.add_argument("--backup", type=Path, help="online-backup the target here before writing")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    li = _load_legacy_import(args.module)
    tolerance = (
        args.tolerance_seconds
        if args.tolerance_seconds is not None
        else li.DEFAULT_DEDUPE_TOLERANCE_SECONDS
    )

    if args.backup and not args.dry_run:
        _online_backup(args.target, args.backup, args.busy_timeout_ms)

    conn = sqlite3.connect(args.target, timeout=args.busy_timeout_ms / 1000)
    try:
        conn.execute(f"PRAGMA busy_timeout = {int(args.busy_timeout_ms)}")
        # A large page cache keeps the index B-trees in memory while the
        # copy runs under the write lock — the live integration's writers
        # wait on that lock (Python's default sqlite timeout is 5 s), so
        # the shorter it's held the better.
        conn.execute("PRAGMA cache_size = -262144")  # 256 MiB
        conn.execute("PRAGMA temp_store = MEMORY")
        summary = li.import_legacy_window(
            conn,
            args.source,
            since=args.since,
            until=args.until,
            tolerance_seconds=tolerance,
            dry_run=args.dry_run,
        )
    except li.LegacyImportError as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    finally:
        conn.close()

    print(json.dumps({"dry_run": args.dry_run, **summary}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
