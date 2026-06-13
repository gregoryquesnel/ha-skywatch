"""Aircraft classification helpers — pure Python, no HA imports.

Replaces the legacy Jinja macros `helo_codes()` and
`is_regina_police_unit()` from ha-tinker's `custom_templates/ha_macros.jinja`.
Macros aren't HACS-distributable; equivalent logic moves here so the
integration computes the category server-side and exposes it via
`binary_sensor.skywatch_helicopter_overhead` etc.

The watch matcher is the generalization of `is_regina_police_unit`:
instead of hardcoding C-GRPF, the user configures any number of watch
entries via the options flow. Each entry can match by registration,
or by FR24 privacy-block fingerprint (callsign='Blocked' AND
registration IS NULL AND aircraft_code matches the fingerprint).
"""

from __future__ import annotations

from dataclasses import dataclass


def is_helicopter(aircraft_code: str | None, helo_codes: tuple[str, ...]) -> bool:
    """True if aircraft_code is in helo_codes (case-insensitive)."""
    if not aircraft_code:
        return False
    return aircraft_code.upper() in {c.upper() for c in helo_codes}


def is_military(aircraft_code: str | None, military_codes: tuple[str, ...]) -> bool:
    """True if aircraft_code is in military_codes (case-insensitive)."""
    if not aircraft_code:
        return False
    return aircraft_code.upper() in {c.upper() for c in military_codes}


@dataclass(frozen=True)
class WatchEntry:
    """One watch-list configuration entry.

    Matches in priority order:
      1. registration exact (case-insensitive)
      2. aircraft_code fingerprint AND callsign='Blocked' AND registration IS NULL
         (FR24 privacy-block escape — for Regina Police Air Unit C-GRPF
         and any similar privacy-suppressed airframe)

    `slug` is the entity_id suffix — `binary_sensor.skywatch_watch_<slug>`.
    """

    slug: str
    label: str
    registration: str | None = None
    aircraft_code: str | None = None
    match_blocked: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> WatchEntry:
        slug = data.get("slug")
        if not slug:
            raise ValueError("WatchEntry requires a 'slug' field")
        label = data.get("label") or slug
        return cls(
            slug=str(slug),
            label=str(label),
            registration=data.get("registration") or None,
            aircraft_code=data.get("aircraft_code") or None,
            match_blocked=bool(data.get("match_blocked", False)),
        )


def match_watch(
    flight: dict,
    watch_entries: tuple[WatchEntry, ...],
) -> WatchEntry | None:
    """Return the first watch entry that matches the flight, or None.

    `flight` is a dict with at least: registration, aircraft_code, callsign.
    """
    reg = (flight.get("aircraft_registration") or flight.get("registration") or "").upper()
    code = (flight.get("aircraft_code") or "").upper()
    callsign = flight.get("callsign") or ""

    for entry in watch_entries:
        if entry.registration and reg and entry.registration.upper() == reg:
            return entry
        if (
            entry.match_blocked
            and entry.aircraft_code
            and entry.aircraft_code.upper() == code
            and callsign == "Blocked"
            and not reg
        ):
            return entry
    return None
