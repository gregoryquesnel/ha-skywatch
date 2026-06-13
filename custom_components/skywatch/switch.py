"""Skywatch switch platform.

Single entity: `switch.skywatch_alerts_enabled` — master gate for the
aircraft-entry-alert blueprint. Off = mute all aircraft alerts (matching
ha-tinker's input_boolean.sky_alerts_enabled semantics).

State persists across HA restarts via RestoreEntity. The integration
doesn't react to the switch directly; the alert blueprint references
this entity in its enable_toggle input and the blueprint's template
condition gates on its state.

Future v0.3: per-watch alert toggles (matching ha-tinker's
input_boolean.police_air_alerts_enabled) would follow the same pattern,
one switch per WatchEntry slug.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity

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
    async_add_entities([SkywatchAlertsEnabledSwitch(coordinator)])


class SkywatchAlertsEnabledSwitch(SwitchEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "alerts_enabled"
    _attr_name = "Alerts enabled"
    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator: SkywatchCoordinator) -> None:
        entry = coordinator.config_entry  # type: ignore[union-attr]
        self._attr_unique_id = f"{entry.entry_id}_alerts_enabled"
        self._attr_device_info = build_device_info(entry)
        self._is_on = True  # default-on; restored from registry if known

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in ("on", "off"):
            self._is_on = last.state == "on"

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._is_on = False
        self.async_write_ha_state()
