"""Skywatch number platform.

Single entity: `number.skywatch_sightings_page` — the recent-sightings
pagination cursor as a native HA entity. Reads/writes the coordinator's
current_page; tapping the +/- buttons (or the numeric-input feature on a
tile) calls async_set_page just like the skywatch.set_page service does.

Why a native entity instead of asking users to create an input_number?
Modern HA integrations ship their own controls — FR24 does this with
`text.flightradar24_add_to_track`, recorder with `number.recorder_*`,
etc. Native entities show up in Settings → Devices & Services →
Skywatch automatically, persist via the entity registry, and don't
require any user YAML.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._device import build_device_info
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
    async_add_entities([SkywatchLogPageNumber(coordinator)])


class SkywatchLogPageNumber(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "sightings_page"
    _attr_name = "Sightings page"
    _attr_icon = "mdi:format-list-numbered"
    _attr_native_min_value = 1
    _attr_native_max_value = 9999  # coordinator clamps to total_pages
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: SkywatchCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry  # type: ignore[union-attr]
        self._attr_unique_id = f"{entry.entry_id}_sightings_page"
        self._attr_device_info = build_device_info(entry)

    @property
    def native_value(self) -> float:
        return float(self.coordinator.current_page)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_page(int(value))
