"""Boundary normalizers for payload fields and ISO timestamps."""

from __future__ import annotations

from datetime import UTC, datetime


def normalize_photo_url(value: object) -> str | None:
    """Strip the malformed 'https:https://' prefix.

    FR24's HA integration occasionally produced URLs with the protocol
    doubled. Recent builds emit clean URLs, but historic DB rows still
    carry the corruption and the upstream bug can regress. Sanitizing at
    the insertion boundary means downstream consumers never see it.
    """
    if not value:
        return None
    if isinstance(value, str) and value.startswith("https:https://"):
        return value[6:]
    return value if isinstance(value, str) else None


def coerce_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def coerce_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp into an aware UTC datetime.

    Tolerates both 'Z' Zulu-suffix and naive (no-TZ) strings — naive values
    are treated as UTC so arithmetic with the result never raises. The
    legacy insert path always wrote aware ISO; older migrated rows or
    rows from external inserts may not.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
