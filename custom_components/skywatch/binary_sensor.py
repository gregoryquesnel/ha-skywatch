"""Skywatch binary sensor platform.

Two live binary sensors derived from the source's current_flights()
snapshot. Both bypass the coordinator's data dict so they reflect the
real-time source state, not the 30 s refresh tick.

  skywatch_has_aircraft        — at least one aircraft in watch radius
  skywatch_helicopter_overhead — at least one in-radius aircraft whose
                                 ICAO type designator is in the configured
                                 helo_codes list
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._device import build_device_info
from .classify import is_helicopter
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import SkywatchCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SkywatchCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SkywatchHasAircraftBinarySensor(coordinator),
            SkywatchHelicopterOverheadBinarySensor(coordinator),
        ]
    )


class SkywatchHasAircraftBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "has_aircraft"
    _attr_name = "Aircraft present"
    _attr_icon = "mdi:airplane"

    def __init__(self, coordinator: SkywatchCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry  # type: ignore[union-attr]
        self._attr_unique_id = f"{entry.entry_id}_has_aircraft"
        self._attr_device_info = build_device_info(entry)

    @property
    def is_on(self) -> bool:
        return len(self.coordinator.source.current_flights()) > 0


class SkywatchHelicopterOverheadBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "helicopter_overhead"
    _attr_name = "Helicopter overhead"
    _attr_icon = "mdi:helicopter"

    def __init__(self, coordinator: SkywatchCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry  # type: ignore[union-attr]
        self._attr_unique_id = f"{entry.entry_id}_helicopter_overhead"
        self._attr_device_info = build_device_info(entry)

    @property
    def is_on(self) -> bool:
        flights = self.coordinator.source.current_flights()
        return any(
            is_helicopter(f.get("aircraft_code"), self.coordinator.helo_codes) for f in flights
        )

    @property
    def extra_state_attributes(self) -> dict | None:
        flights = self.coordinator.source.current_flights()
        helo_callsigns = [
            f.get("callsign")
            for f in flights
            if is_helicopter(f.get("aircraft_code"), self.coordinator.helo_codes)
        ]
        return {"helicopters": [c for c in helo_callsigns if c]}
