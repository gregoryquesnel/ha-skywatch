"""Skywatch button platform.

Single entity: `button.skywatch_clear_search` — convenience for resetting
the search term to empty. Matches the ha-tinker dashboard's 'Clear
search' button.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
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
    async_add_entities([SkywatchClearSearchButton(coordinator)])


class SkywatchClearSearchButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "clear_search"
    _attr_name = "Clear search"
    _attr_icon = "mdi:close-circle-outline"

    def __init__(self, coordinator: SkywatchCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry  # type: ignore[union-attr]
        self._attr_unique_id = f"{entry.entry_id}_clear_search"
        self._attr_device_info = build_device_info(entry)

    async def async_press(self) -> None:
        await self.coordinator.async_set_search_term("")
