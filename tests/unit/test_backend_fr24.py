"""FR24 payload-to-normalized-model translation.

Tests the pure translation layer — async_setup/_teardown (which require
HA core) are exercised in the later HA integration test phase.
"""

from __future__ import annotations

import inspect
import sys
import types
from dataclasses import dataclass, field
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
    async def test_emits_normalized_entry(self, src: Fr24Source) -> None:
        captured: list[Entry] = []
        src.on_entry(captured.append)

        await src._handle_entry(FakeEvent(ENTRY_PAYLOAD))

        assert len(captured) == 1
        e = captured[0]
        assert e.flight_id == "flight_abc123"
        assert e.callsign == "ACA123"
        assert e.aircraft_code == "B738"
        # entry_time is set to "now" — must be aware UTC.
        assert e.entry_time.tzinfo is not None

    async def test_missing_id_emits_nothing(self, src: Fr24Source) -> None:
        captured: list[Entry] = []
        src.on_entry(captured.append)
        await src._handle_entry(FakeEvent(MALFORMED_PAYLOAD))
        assert captured == []

    async def test_non_dict_payload_does_not_raise(self, src: Fr24Source) -> None:
        # The provider may produce malformed events; we must degrade
        # gracefully rather than crash the integration.
        await src._handle_entry(FakeEvent(data=None))  # type: ignore[arg-type]


class TestExitTranslation:
    async def test_emits_normalized_sighting_with_flight_id(self, src: Fr24Source) -> None:
        captured: list[tuple] = []
        src.on_exit(lambda fid, sig: captured.append((fid, sig)))

        await src._handle_exit(FakeEvent(EXIT_PAYLOAD))

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

    async def test_doubled_https_photo_stripped(self, src: Fr24Source) -> None:
        captured: list[tuple] = []
        src.on_exit(lambda fid, sig: captured.append((fid, sig)))

        await src._handle_exit(FakeEvent(EXIT_PAYLOAD_WITH_DOUBLED_PHOTO))

        _, sig = captured[0]
        assert sig.aircraft_photo == "https://cdn.jetphotos.com/200/photo.jpg"

    async def test_blocked_payload_preserves_fingerprint_fields(self, src: Fr24Source) -> None:
        # Privacy-blocked aircraft (C-GRPF style): registration is null,
        # callsign is literal "Blocked" — the watch matcher uses
        # aircraft_code as the fingerprint.
        captured: list[tuple] = []
        src.on_exit(lambda fid, sig: captured.append((fid, sig)))

        await src._handle_exit(FakeEvent(BLOCKED_EXIT_PAYLOAD))

        _, sig = captured[0]
        assert sig.callsign == "Blocked"
        assert sig.aircraft_code == "C182"
        assert sig.registration is None


class TestMovementTranslation:
    async def test_landed_uses_destination_airport(self, src: Fr24Source) -> None:
        captured: list[Movement] = []
        src.on_landing(captured.append)

        await src._handle_landed(FakeEvent(LANDED_PAYLOAD))

        assert len(captured) == 1
        m = captured[0]
        assert m.direction == "landed"
        assert m.airport_iata == "YQR"  # destination
        assert m.callsign == "WJA802"

    async def test_took_off_uses_origin_airport(self, src: Fr24Source) -> None:
        captured: list[Movement] = []
        src.on_takeoff(captured.append)

        await src._handle_took_off(FakeEvent(TOOK_OFF_PAYLOAD))

        m = captured[0]
        assert m.direction == "took_off"
        assert m.airport_iata == "YQR"  # origin

    async def test_movement_emits_now_utc(self, src: Fr24Source) -> None:
        captured: list[Movement] = []
        src.on_landing(captured.append)
        before = datetime.now(UTC)
        await src._handle_landed(FakeEvent(LANDED_PAYLOAD))
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


@dataclass
class FakeBus:
    """Records what Fr24Source.async_setup hands to hass.bus.async_listen."""

    listeners: dict = field(default_factory=dict)

    def async_listen(self, event_type: str, handler):
        self.listeners[event_type] = handler
        return lambda: self.listeners.pop(event_type, None)


@dataclass
class FakeConfigEntries:
    def async_entries(self, domain: str) -> list:
        return [object()] if domain == "flightradar24" else []


@dataclass
class FakeHass:
    bus: FakeBus = field(default_factory=FakeBus)
    config_entries: FakeConfigEntries = field(default_factory=FakeConfigEntries)


def _runs_on_event_loop(handler) -> bool:
    """True if HA's bus would run this handler on the event loop.

    HA dispatches coroutine functions and @callback-decorated functions
    (which carry `_hass_callback = True`) on the loop; everything else is
    sent to the executor thread pool.
    """
    target = getattr(handler, "__func__", handler)
    return inspect.iscoroutinefunction(target) or getattr(target, "_hass_callback", False)


@pytest.fixture
def ha_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """async_setup imports ConfigEntryNotReady lazily; stub it without HA.

    The unit-test CI job doesn't install homeassistant.
    """
    try:
        import homeassistant.exceptions  # noqa: F401, PLC0415
    except ImportError:
        ha = types.ModuleType("homeassistant")
        exc = types.ModuleType("homeassistant.exceptions")
        exc.ConfigEntryNotReady = type("ConfigEntryNotReady", (Exception,), {})  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "homeassistant", ha)
        monkeypatch.setitem(sys.modules, "homeassistant.exceptions", exc)


class TestBusHandlersRunOnEventLoop:
    """Regression: plain-def handlers ran in the executor.

    The coordinator's listeners call hass.bus.async_fire and
    hass.async_create_task, which HA raises on when called off the event
    loop. With sync handlers, no skywatch_sighting events fired and no
    entries, exits or movements were persisted (2026-06-13 to 2026-10-10).
    """

    @pytest.mark.parametrize(
        "name", ["_handle_entry", "_handle_exit", "_handle_landed", "_handle_took_off"]
    )
    def test_handler_is_loop_safe(self, name: str) -> None:
        assert _runs_on_event_loop(getattr(Fr24Source, name)), (
            f"Fr24Source.{name} would run in the executor; make it async or @callback"
        )

    async def test_every_registered_listener_is_loop_safe(self, ha_exceptions) -> None:
        hass = FakeHass()
        src = Fr24Source(hass=hass)  # type: ignore[arg-type]
        await src.async_setup()

        assert set(hass.bus.listeners) == {
            EVENT_ENTRY,
            EVENT_EXIT,
            EVENT_AREA_LANDED,
            EVENT_AREA_TOOK_OFF,
        }
        for event_type, handler in hass.bus.listeners.items():
            assert _runs_on_event_loop(handler), f"{event_type} handler would run off-loop"

        await src.async_teardown()
        assert hass.bus.listeners == {}

    async def test_bus_dispatch_reaches_listener(self, ha_exceptions) -> None:
        """An event delivered the way HA delivers it ends at the coordinator listener."""
        hass = FakeHass()
        src = Fr24Source(hass=hass)  # type: ignore[arg-type]
        await src.async_setup()
        entries: list[Entry] = []
        exits: list[tuple[str | None, Sighting]] = []
        src.on_entry(entries.append)
        src.on_exit(lambda fid, s: exits.append((fid, s)))

        await hass.bus.listeners[EVENT_ENTRY](FakeEvent(ENTRY_PAYLOAD))
        await hass.bus.listeners[EVENT_EXIT](FakeEvent(EXIT_PAYLOAD))

        assert [e.flight_id for e in entries] == ["flight_abc123"]
        assert len(exits) == 1
