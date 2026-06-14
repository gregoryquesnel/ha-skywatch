"""Flightradar24 HACS-integration source adapter.

Subscribes to four FR24 events on the HA bus and translates each payload
to the integration's normalized models. The coordinator listens for the
emitted events; this module never touches storage or sensors.

FR24 event payload fields (per AlexandrErohin/home-assistant-flightradar24):
  - id                              str   flight tracking id
  - callsign                        str?  "ACA123" | "Blocked" | None
  - flight_number                   str?  "AC123" | None
  - aircraft_code                   str?  ICAO type designator
  - aircraft_model                  str?  human-readable
  - aircraft_registration           str?  tail number
  - airline / airline_iata          str?
  - airport_origin_code_iata        str?
  - airport_origin_city             str?
  - airport_destination_code_iata   str?
  - airport_destination_city        str?
  - altitude                        int   feet
  - ground_speed                    int   knots
  - heading                         int   degrees
  - vertical_speed                  int   ft/min
  - closest_distance                float km
  - aircraft_photo_small            str?  URL
  - tracked_by_device               str?  HA device_id
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ..const import SOURCE_FR24
from ..models import Entry, Movement, Sighting
from ..storage import coerce_float, coerce_int, normalize_photo_url
from .base import Source

if TYPE_CHECKING:
    from homeassistant.core import Event, HomeAssistant

FR24_DOMAIN = "flightradar24"

EVENT_ENTRY = "flightradar24_entry"
EVENT_EXIT = "flightradar24_exit"
EVENT_AREA_LANDED = "flightradar24_area_landed"
EVENT_AREA_TOOK_OFF = "flightradar24_area_took_off"

FR24_LIVE_SENSOR = "sensor.flightradar24_current_in_area"


class Fr24Source(Source):
    """Adapter for the Flightradar24 HACS integration."""

    source_id = SOURCE_FR24

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__()
        self._hass = hass
        self._unsubs: list = []

    async def async_setup(self) -> None:
        # ConfigEntryNotReady is imported inside the function so the
        # backend module can be imported without homeassistant installed —
        # unit tests for the translation layer (_payload_to_entry etc.)
        # exercise only the pure-Python helpers and don't need HA.
        from homeassistant.exceptions import ConfigEntryNotReady  # noqa: PLC0415

        if not self._hass.config_entries.async_entries(FR24_DOMAIN):
            raise ConfigEntryNotReady(
                "Skywatch requires the Flightradar24 HACS integration "
                "(AlexandrErohin/home-assistant-flightradar24). "
                "Install + configure it before adding Skywatch."
            )
        bus = self._hass.bus
        self._unsubs = [
            bus.async_listen(EVENT_ENTRY, self._handle_entry),
            bus.async_listen(EVENT_EXIT, self._handle_exit),
            bus.async_listen(EVENT_AREA_LANDED, self._handle_landed),
            bus.async_listen(EVENT_AREA_TOOK_OFF, self._handle_took_off),
        ]

    async def async_teardown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []

    def current_flights(self) -> list[dict]:
        state = self._hass.states.get(FR24_LIVE_SENSOR)
        if state is None:
            return []
        flights = state.attributes.get("flights")
        return list(flights) if isinstance(flights, list) else []

    def watched_entities(self) -> list[str]:
        """FR24's `current_in_area` sensor — every state change is a new poll."""
        return [FR24_LIVE_SENSOR]

    def _handle_entry(self, event: Event) -> None:
        entry = self._payload_to_entry(event.data)
        if entry is not None:
            self._emit_entry(entry)

    def _handle_exit(self, event: Event) -> None:
        flight_id = event.data.get("id") if isinstance(event.data, dict) else None
        sighting = self._payload_to_sighting(event.data)
        if sighting is not None:
            self._emit_exit(flight_id, sighting)

    def _handle_landed(self, event: Event) -> None:
        movement = self._payload_to_movement(event.data, direction="landed")
        if movement is not None:
            self._emit_landing(movement)

    def _handle_took_off(self, event: Event) -> None:
        movement = self._payload_to_movement(event.data, direction="took_off")
        if movement is not None:
            self._emit_takeoff(movement)

    @staticmethod
    def _payload_to_entry(payload: object) -> Entry | None:
        if not isinstance(payload, dict):
            return None
        flight_id = payload.get("id")
        if not flight_id:
            return None
        return Entry(
            flight_id=str(flight_id),
            entry_time=datetime.now(UTC),
            callsign=payload.get("callsign") or None,
            flight_number=payload.get("flight_number") or None,
            aircraft_code=payload.get("aircraft_code") or None,
            aircraft_model=payload.get("aircraft_model") or None,
        )

    @staticmethod
    def _payload_to_sighting(payload: object) -> Sighting | None:
        if not isinstance(payload, dict):
            return None
        return Sighting(
            exit_time=datetime.now(UTC),
            entry_time=None,
            flight_number=payload.get("flight_number") or None,
            callsign=payload.get("callsign") or None,
            airline=payload.get("airline") or None,
            airline_iata=payload.get("airline_iata") or None,
            aircraft_code=payload.get("aircraft_code") or None,
            aircraft_model=payload.get("aircraft_model") or None,
            registration=payload.get("aircraft_registration") or None,
            origin_iata=payload.get("airport_origin_code_iata") or None,
            origin_city=payload.get("airport_origin_city") or None,
            destination_iata=payload.get("airport_destination_code_iata") or None,
            destination_city=payload.get("airport_destination_city") or None,
            altitude_ft=coerce_int(payload.get("altitude")),
            ground_speed_kt=coerce_int(payload.get("ground_speed")),
            closest_km=coerce_float(payload.get("closest_distance")),
            aircraft_photo=normalize_photo_url(payload.get("aircraft_photo_small")),
            tracked_by_device=payload.get("tracked_by_device") or None,
            heading=coerce_int(payload.get("heading")),
            vertical_speed=coerce_int(payload.get("vertical_speed")),
        )

    @staticmethod
    def _payload_to_movement(payload: object, direction: str) -> Movement | None:
        if not isinstance(payload, dict):
            return None
        if direction == "landed":
            airport = payload.get("airport_destination_code_iata") or None
        else:
            airport = payload.get("airport_origin_code_iata") or None
        return Movement(
            event_time=datetime.now(UTC),
            direction=direction,
            airport_iata=airport,
            flight_number=payload.get("flight_number") or None,
            callsign=payload.get("callsign") or None,
            airline=payload.get("airline") or None,
            airline_iata=payload.get("airline_iata") or None,
            aircraft_code=payload.get("aircraft_code") or None,
            aircraft_model=payload.get("aircraft_model") or None,
            registration=payload.get("aircraft_registration") or None,
            origin_iata=payload.get("airport_origin_code_iata") or None,
            destination_iata=payload.get("airport_destination_code_iata") or None,
            aircraft_photo=normalize_photo_url(payload.get("aircraft_photo_small")),
        )
