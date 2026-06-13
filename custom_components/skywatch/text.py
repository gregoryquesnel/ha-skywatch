"""Skywatch text platform.

Single entity: `text.skywatch_search_term` — the substring filter for
sensor.skywatch_search_results. Setting it triggers a coordinator
refresh; clearing it (empty string) makes the search sensor revert to
its empty-state shape.

Pairs with `button.skywatch_clear_search` (button.py) for the
'reset on tap' affordance ha-tinker has.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.text import TextEntity, TextMode
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
    async_add_entities([SkywatchSearchTermText(coordinator)])


class SkywatchSearchTermText(CoordinatorEntity, TextEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "search_term"
    _attr_name = "Search term"
    _attr_icon = "mdi:magnify"
    _attr_native_min = 0
    _attr_native_max = 100
    _attr_mode = TextMode.TEXT

    def __init__(self, coordinator: SkywatchCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry  # type: ignore[union-attr]
        self._attr_unique_id = f"{entry.entry_id}_search_term"
        self._attr_device_info = build_device_info(entry)

    @property
    def native_value(self) -> str:
        return self.coordinator.current_search_term

    async def async_set_value(self, value: str) -> None:
        await self.coordinator.async_set_search_term(value)
