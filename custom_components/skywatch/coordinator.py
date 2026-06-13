"""Skywatch DataUpdateCoordinator.

Bridges the source-adapter event stream and the storage layer. Owns the
SQLite connection (opened in `async_setup`, closed in `async_unload`)
and runs the pure `build_data` function on every refresh tick to
assemble the platform-facing data dict.

Sync vs async boundary: storage and data_builder are pure-sync; this
coordinator wraps each sqlite call in `hass.async_add_executor_job` so
the I/O never blocks the event loop. Source event handlers are sync
(see backends/base.py) and schedule async persistence via
`hass.async_create_task`.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .classify import is_helicopter, is_military, match_watch
from .const import DB_FILENAME, DB_SUBDIR, EVENT_SKYWATCH_SIGHTING
from .data_builder import build_data
from .storage import (
    insert_entry,
    insert_movement,
    insert_sighting,
    open_db,
    prune_stale_entries,
    take_entry_time,
)

if TYPE_CHECKING:
    import sqlite3

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .backends import Source
    from .classify import WatchEntry
    from .models import Entry, Movement, Sighting

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)


class SkywatchCoordinator(DataUpdateCoordinator):
    """Bridges source events → storage and exposes assembled data to platforms."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        source: Source,
        *,
        tz: ZoneInfo,
        helo_codes: tuple[str, ...],
        military_codes: tuple[str, ...],
        watch_list: tuple[WatchEntry, ...],
        overhead_distance_km: float = 5.0,
        overhead_altitude_ft: int = 10000,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="skywatch",
            update_interval=UPDATE_INTERVAL,
        )
        self._source = source
        self._tz = tz
        self._helo_codes = helo_codes
        self._military_codes = military_codes
        self._watch_list = watch_list
        self._overhead_distance_km = overhead_distance_km
        self._overhead_altitude_ft = overhead_altitude_ft
        self._conn: sqlite3.Connection | None = None
        self._current_page = 1
        self._current_search = ""
        self._unsub_source_listeners: list = []

    @property
    def source(self) -> Source:
        return self._source

    @property
    def watch_list(self) -> tuple[WatchEntry, ...]:
        return self._watch_list

    @property
    def helo_codes(self) -> tuple[str, ...]:
        return self._helo_codes

    @property
    def military_codes(self) -> tuple[str, ...]:
        return self._military_codes

    async def async_setup(self) -> None:
        db_path = Path(self.hass.config.path(DB_SUBDIR)) / DB_FILENAME
        await self.hass.async_add_executor_job(
            lambda: db_path.parent.mkdir(parents=True, exist_ok=True)
        )
        self._conn = await self.hass.async_add_executor_job(open_db, db_path)
        await self._source.async_setup()
        self._unsub_source_listeners = [
            self._source.on_entry(self._on_entry),
            self._source.on_exit(self._on_exit),
            self._source.on_landing(self._on_landing),
            self._source.on_takeoff(self._on_takeoff),
        ]
        await self.async_config_entry_first_refresh()

    async def async_unload(self) -> None:
        for unsub in self._unsub_source_listeners:
            unsub()
        self._unsub_source_listeners = []
        await self._source.async_teardown()
        if self._conn is not None:
            await self.hass.async_add_executor_job(self._conn.close)
            self._conn = None

    async def async_set_page(self, page: int) -> None:
        self._current_page = max(1, int(page))
        await self.async_request_refresh()

    async def async_set_search_term(self, term: str) -> None:
        self._current_search = str(term).strip()
        await self.async_request_refresh()

    @property
    def current_page(self) -> int:
        return self._current_page

    @property
    def current_search_term(self) -> str:
        return self._current_search

    async def _async_update_data(self) -> dict:
        if self._conn is None:
            return {}
        return await self.hass.async_add_executor_job(self._sync_build_data)

    def _sync_build_data(self) -> dict:
        assert self._conn is not None
        return build_data(
            self._conn,
            tz=self._tz,
            current_page=self._current_page,
            current_search=self._current_search,
            military_codes=self._military_codes,
            watch_list=self._watch_list,
            overhead_distance_km=self._overhead_distance_km,
            overhead_altitude_ft=self._overhead_altitude_ft,
        )

    def _on_entry(self, entry: Entry) -> None:
        self._fire_skywatch_event(
            kind="entry",
            flight_id=entry.flight_id,
            callsign=entry.callsign,
            aircraft_code=entry.aircraft_code,
            aircraft_model=entry.aircraft_model,
            registration=None,
        )
        self.hass.async_create_task(self._async_persist_entry(entry))

    def _on_exit(self, flight_id: str | None, sighting: Sighting) -> None:
        self._fire_skywatch_event(
            kind="exit",
            flight_id=flight_id,
            callsign=sighting.callsign,
            aircraft_code=sighting.aircraft_code,
            aircraft_model=sighting.aircraft_model,
            registration=sighting.registration,
        )
        self.hass.async_create_task(self._async_persist_exit(flight_id, sighting))

    def _on_landing(self, movement: Movement) -> None:
        self._fire_skywatch_event(
            kind="landed",
            flight_id=None,
            callsign=movement.callsign,
            aircraft_code=movement.aircraft_code,
            aircraft_model=movement.aircraft_model,
            registration=movement.registration,
        )
        self.hass.async_create_task(self._async_persist_movement(movement))

    def _on_takeoff(self, movement: Movement) -> None:
        self._fire_skywatch_event(
            kind="took_off",
            flight_id=None,
            callsign=movement.callsign,
            aircraft_code=movement.aircraft_code,
            aircraft_model=movement.aircraft_model,
            registration=movement.registration,
        )
        self.hass.async_create_task(self._async_persist_movement(movement))

    def _fire_skywatch_event(
        self,
        *,
        kind: str,
        flight_id: str | None,
        callsign: str | None,
        aircraft_code: str | None,
        aircraft_model: str | None,
        registration: str | None,
    ) -> None:
        """Fire skywatch_sighting on the HA bus with classification baked in.

        Blueprints listen to this single event instead of FR24-specific
        events so that swapping the source backend doesn't break the
        user's automations.
        """
        watch = match_watch(
            {
                "aircraft_registration": registration,
                "aircraft_code": aircraft_code,
                "callsign": callsign,
            },
            self._watch_list,
        )
        self.hass.bus.async_fire(
            EVENT_SKYWATCH_SIGHTING,
            {
                "kind": kind,
                "flight_id": flight_id,
                "callsign": callsign,
                "aircraft_code": aircraft_code,
                "aircraft_model": aircraft_model,
                "registration": registration,
                "is_helo": is_helicopter(aircraft_code, self._helo_codes),
                "is_military": is_military(aircraft_code, self._military_codes),
                "watch_slug": watch.slug if watch else None,
                "watch_label": watch.label if watch else None,
            },
        )

    async def _async_persist_entry(self, entry: Entry) -> None:
        if self._conn is None:
            return
        await self.hass.async_add_executor_job(self._sync_persist_entry, entry)

    def _sync_persist_entry(self, entry: Entry) -> None:
        assert self._conn is not None
        insert_entry(self._conn, entry)
        prune_stale_entries(self._conn)
        self._conn.commit()

    async def _async_persist_exit(self, flight_id: str | None, sighting: Sighting) -> None:
        if self._conn is None:
            return
        await self.hass.async_add_executor_job(self._sync_persist_exit, flight_id, sighting)
        await self.async_request_refresh()

    def _sync_persist_exit(self, flight_id: str | None, sighting: Sighting) -> None:
        assert self._conn is not None
        entry_time = take_entry_time(self._conn, flight_id)
        if entry_time is not None:
            sighting = replace(sighting, entry_time=entry_time)
        insert_sighting(self._conn, sighting)
        self._conn.commit()

    async def _async_persist_movement(self, movement: Movement) -> None:
        if self._conn is None:
            return
        await self.hass.async_add_executor_job(self._sync_persist_movement, movement)
        await self.async_request_refresh()

    def _sync_persist_movement(self, movement: Movement) -> None:
        assert self._conn is not None
        insert_movement(self._conn, movement)
        self._conn.commit()
