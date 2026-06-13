"""FR24 payload-to-normalized-model translation.

Tests the pure translation layer — async_setup/_teardown (which require
HA core) are exercised in the later HA integration test phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from custom_components.skywatch.backends.fr24 import (
    EVENT_AREA_LANDED,
    EVENT_AREA_TOOK_OFF,
    EVENT_ENTRY,
    EVENT_EXIT,
    Fr24Source,
)
from custom_components.skywatch.const import SOURCE_FR24
from custom_components.skywatch.models import Entry, Movement, Sighting
from tests.fixtures.fr24_payloads import (
    BLOCKED_EXIT_PAYLOAD,
    ENTRY_PAYLOAD,
    EXIT_PAYLOAD,
    EXIT_PAYLOAD_WITH_DOUBLED_PHOTO,
    LANDED_PAYLOAD,
    MALFORMED_PAYLOAD,
    TOOK_OFF_PAYLOAD,
)


@dataclass
class FakeEvent:
    """Stand-in for homeassistant.core.Event for unit tests."""

    data: dict


@pytest.fixture
def src() -> Fr24Source:
    return Fr24Source(hass=None)  # type: ignore[arg-type]


class TestEntryTranslation:
    def test_emits_normalized_entry(self, src: Fr24Source) -> None:
        captured: list[Entry] = []
        src.on_entry(captured.append)

        src._handle_entry(FakeEvent(ENTRY_PAYLOAD))

        assert len(captured) == 1
        e = captured[0]
        assert e.flight_id == "flight_abc123"
        assert e.callsign == "ACA123"
        assert e.aircraft_code == "B738"
        # entry_time is set to "now" — must be aware UTC.
        assert e.entry_time.tzinfo is not None

    def test_missing_id_emits_nothing(self, src: Fr24Source) -> None:
        captured: list[Entry] = []
        src.on_entry(captured.append)
        src._handle_entry(FakeEvent(MALFORMED_PAYLOAD))
        assert captured == []

    def test_non_dict_payload_does_not_raise(self, src: Fr24Source) -> None:
        # The provider may produce malformed events; we must degrade
        # gracefully rather than crash the integration.
        src._handle_entry(FakeEvent(data=None))  # type: ignore[arg-type]


class TestExitTranslation:
    def test_emits_normalized_sighting_with_flight_id(self, src: Fr24Source) -> None:
        captured: list[tuple] = []
        src.on_exit(lambda fid, sig: captured.append((fid, sig)))

        src._handle_exit(FakeEvent(EXIT_PAYLOAD))

        assert len(captured) == 1
        fid, sig = captured[0]
        assert fid == "flight_abc123"
        assert isinstance(sig, Sighting)
        assert sig.callsign == "ACA123"
        assert sig.airline == "Air Canada"
        assert sig.registration == "C-FGAR"
        # entry_time is None on source emit; coordinator joins from DB.
        assert sig.entry_time is None
        # exit_time stamped "now" (aware UTC).
        assert sig.exit_time.tzinfo is not None
        # Numeric fields coerced.
        assert sig.altitude_ft == 12000
        assert sig.closest_km == pytest.approx(3.2)

    def test_doubled_https_photo_stripped(self, src: Fr24Source) -> None:
        captured: list[tuple] = []
        src.on_exit(lambda fid, sig: captured.append((fid, sig)))

        src._handle_exit(FakeEvent(EXIT_PAYLOAD_WITH_DOUBLED_PHOTO))

        _, sig = captured[0]
        assert sig.aircraft_photo == "https://cdn.jetphotos.com/200/photo.jpg"

    def test_blocked_payload_preserves_fingerprint_fields(self, src: Fr24Source) -> None:
        # Privacy-blocked aircraft (C-GRPF style): registration is null,
        # callsign is literal "Blocked" — the watch matcher uses
        # aircraft_code as the fingerprint.
        captured: list[tuple] = []
        src.on_exit(lambda fid, sig: captured.append((fid, sig)))

        src._handle_exit(FakeEvent(BLOCKED_EXIT_PAYLOAD))

        _, sig = captured[0]
        assert sig.callsign == "Blocked"
        assert sig.aircraft_code == "C182"
        assert sig.registration is None


class TestMovementTranslation:
    def test_landed_uses_destination_airport(self, src: Fr24Source) -> None:
        captured: list[Movement] = []
        src.on_landing(captured.append)

        src._handle_landed(FakeEvent(LANDED_PAYLOAD))

        assert len(captured) == 1
        m = captured[0]
        assert m.direction == "landed"
        assert m.airport_iata == "YQR"  # destination
        assert m.callsign == "WJA802"

    def test_took_off_uses_origin_airport(self, src: Fr24Source) -> None:
        captured: list[Movement] = []
        src.on_takeoff(captured.append)

        src._handle_took_off(FakeEvent(TOOK_OFF_PAYLOAD))

        m = captured[0]
        assert m.direction == "took_off"
        assert m.airport_iata == "YQR"  # origin

    def test_movement_emits_now_utc(self, src: Fr24Source) -> None:
        captured: list[Movement] = []
        src.on_landing(captured.append)
        before = datetime.now(UTC)
        src._handle_landed(FakeEvent(LANDED_PAYLOAD))
        after = datetime.now(UTC)
        assert before <= captured[0].event_time <= after


class TestEventNames:
    def test_constants_match_fr24_integration_event_names(self) -> None:
        # Pinning these — if FR24 renames its events upstream the
        # integration must consciously bump (and likely update the
        # min-version constraint).
        assert EVENT_ENTRY == "flightradar24_entry"
        assert EVENT_EXIT == "flightradar24_exit"
        assert EVENT_AREA_LANDED == "flightradar24_area_landed"
        assert EVENT_AREA_TOOK_OFF == "flightradar24_area_took_off"


class TestSourceIdentity:
    def test_source_id_is_fr24(self, src: Fr24Source) -> None:
        assert src.source_id == SOURCE_FR24
