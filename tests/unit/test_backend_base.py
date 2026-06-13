"""Listener registration / emission semantics of the Source base."""

from __future__ import annotations

from datetime import UTC, datetime

from custom_components.skywatch.backends.base import Source
from custom_components.skywatch.models import Entry, Movement, Sighting


class _FakeSource(Source):
    """Concrete Source for testing — no real provider hookup."""

    async def async_setup(self) -> None:
        return None

    async def async_teardown(self) -> None:
        return None


def _entry() -> Entry:
    return Entry(flight_id="abc", entry_time=datetime.now(UTC), callsign="X")


def _sighting() -> Sighting:
    return Sighting(exit_time=datetime.now(UTC))


def _movement(direction: str) -> Movement:
    return Movement(event_time=datetime.now(UTC), direction=direction)


class TestListenerRegistration:
    def test_on_entry_fires_for_each_listener(self) -> None:
        src = _FakeSource()
        received: list[Entry] = []
        src.on_entry(received.append)
        src.on_entry(received.append)
        src._emit_entry(_entry())
        assert len(received) == 2

    def test_unsub_removes_listener(self) -> None:
        src = _FakeSource()
        received: list[Entry] = []
        unsub = src.on_entry(received.append)
        src._emit_entry(_entry())
        unsub()
        src._emit_entry(_entry())
        assert len(received) == 1

    def test_unsub_twice_is_safe(self) -> None:
        src = _FakeSource()
        unsub = src.on_entry(lambda _: None)
        unsub()
        unsub()  # no exception expected

    def test_on_exit_passes_flight_id_and_sighting(self) -> None:
        src = _FakeSource()
        captured: list[tuple] = []
        src.on_exit(lambda fid, sig: captured.append((fid, sig)))
        s = _sighting()
        src._emit_exit("flight_id_123", s)
        assert captured == [("flight_id_123", s)]

    def test_on_exit_handles_none_flight_id(self) -> None:
        src = _FakeSource()
        captured: list[tuple] = []
        src.on_exit(lambda fid, sig: captured.append((fid, sig)))
        src._emit_exit(None, _sighting())
        assert captured[0][0] is None

    def test_landing_and_takeoff_listeners_independent(self) -> None:
        src = _FakeSource()
        landed: list[Movement] = []
        took_off: list[Movement] = []
        src.on_landing(landed.append)
        src.on_takeoff(took_off.append)

        src._emit_landing(_movement("landed"))
        src._emit_takeoff(_movement("took_off"))

        assert len(landed) == 1
        assert len(took_off) == 1
        assert landed[0].direction == "landed"
        assert took_off[0].direction == "took_off"


class TestCurrentFlights:
    def test_default_returns_empty(self) -> None:
        src = _FakeSource()
        assert src.current_flights() == []
