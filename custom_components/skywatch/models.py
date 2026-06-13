"""Normalized internal models.

Source adapters (backends/) translate raw provider payloads into these
shapes; storage and coordinator consume only these. Changing a backend
should never require touching coordinator/storage code — that's the
contract this module exists to enforce.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Entry:
    """An aircraft that just entered the watch radius (transient).

    Stored briefly to be joined with the matching Sighting on exit so the
    integration can compute dwell_seconds. TTL-pruned after 2 h.
    """

    flight_id: str
    entry_time: datetime
    callsign: str | None = None
    flight_number: str | None = None
    aircraft_code: str | None = None
    aircraft_model: str | None = None


@dataclass(frozen=True)
class Sighting:
    """An aircraft that completed a transit of the watch radius.

    The persistent record. entry_time is None for rows that pre-date
    entry capture (legacy import, or aircraft that was already inside
    the radius when the integration started).
    """

    exit_time: datetime
    entry_time: datetime | None = None
    flight_number: str | None = None
    callsign: str | None = None
    airline: str | None = None
    airline_iata: str | None = None
    aircraft_code: str | None = None
    aircraft_model: str | None = None
    registration: str | None = None
    origin_iata: str | None = None
    origin_city: str | None = None
    destination_iata: str | None = None
    destination_city: str | None = None
    altitude_ft: int | None = None
    ground_speed_kt: int | None = None
    closest_km: float | None = None
    aircraft_photo: str | None = None
    tracked_by_device: str | None = None
    heading: int | None = None
    vertical_speed: int | None = None
    on_ground: bool | None = None


@dataclass(frozen=True)
class Movement:
    """A takeoff or landing at a tracked airport."""

    event_time: datetime
    direction: str  # "landed" | "took_off"
    airport_iata: str | None = None
    flight_number: str | None = None
    callsign: str | None = None
    airline: str | None = None
    airline_iata: str | None = None
    aircraft_code: str | None = None
    aircraft_model: str | None = None
    registration: str | None = None
    origin_iata: str | None = None
    destination_iata: str | None = None
    aircraft_photo: str | None = None
