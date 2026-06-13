"""Source adapter abstract base.

A `Source` subscribes to a provider-specific event stream, translates raw
payloads into the integration's normalized models (Entry / Sighting /
Movement), and emits them to listeners. The coordinator registers
listeners for persistence; the rest of the integration never sees a raw
provider payload.

Adding a new backend (dump1090, tar1090, ADSB-Hub) means subclassing
`Source`, implementing `async_setup` / `async_teardown`, and calling
`_emit_*` from its event handlers. Storage, coordinator, and platforms
remain unchanged.

The listener pattern is sync — callbacks fire in the same task that
processes the provider event. If a callback needs async work (e.g.
sqlite write via `hass.async_add_executor_job`), it schedules it via
`hass.async_create_task` and returns immediately.
"""

from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from collections.abc import Callable

from ..models import Entry, Movement, Sighting

EntryListener = Callable[[Entry], None]
ExitListener = Callable[[str | None, Sighting], None]
MovementListener = Callable[[Movement], None]


class Source(ABC):
    """Abstract aircraft-event source."""

    def __init__(self) -> None:
        self._entry_listeners: list[EntryListener] = []
        self._exit_listeners: list[ExitListener] = []
        self._landing_listeners: list[MovementListener] = []
        self._takeoff_listeners: list[MovementListener] = []

    @abstractmethod
    async def async_setup(self) -> None:
        """Subscribe to the provider's event stream.

        Implementations should raise homeassistant.exceptions.ConfigEntryNotReady
        if the provider isn't available yet — HA will retry the setup later.
        """

    @abstractmethod
    async def async_teardown(self) -> None:
        """Unsubscribe and release resources. Called on config entry unload."""

    def current_flights(self) -> list[dict]:
        """Snapshot of flights currently in the watch radius.

        Used by the Leaflet map endpoint. Default implementation returns
        an empty list — subclasses override.

        Each dict carries at minimum: flight_id, callsign, latitude,
        longitude, altitude_ft, heading, ground_speed_kt, aircraft_code,
        on_ground. The integration adds category fields (is_helo,
        is_military, watch_label) over the top.
        """
        return []

    def on_entry(self, callback: EntryListener) -> Callable[[], None]:
        return self._register(self._entry_listeners, callback)

    def on_exit(self, callback: ExitListener) -> Callable[[], None]:
        return self._register(self._exit_listeners, callback)

    def on_landing(self, callback: MovementListener) -> Callable[[], None]:
        return self._register(self._landing_listeners, callback)

    def on_takeoff(self, callback: MovementListener) -> Callable[[], None]:
        return self._register(self._takeoff_listeners, callback)

    @staticmethod
    def _register(listeners: list, callback) -> Callable[[], None]:
        listeners.append(callback)

        def unsub() -> None:
            with contextlib.suppress(ValueError):
                listeners.remove(callback)

        return unsub

    def _emit_entry(self, entry: Entry) -> None:
        for cb in list(self._entry_listeners):
            cb(entry)

    def _emit_exit(self, flight_id: str | None, sighting: Sighting) -> None:
        for cb in list(self._exit_listeners):
            cb(flight_id, sighting)

    def _emit_landing(self, movement: Movement) -> None:
        for cb in list(self._landing_listeners):
            cb(movement)

    def _emit_takeoff(self, movement: Movement) -> None:
        for cb in list(self._takeoff_listeners):
            cb(movement)
