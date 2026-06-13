"""Shared DeviceInfo helper.

Every Skywatch entity binds to a single virtual 'Skywatch' device. That
gives the user one collapsible card in Settings → Devices & Services →
Skywatch instead of 13 loose entities, and — more importantly — makes
HA slugify entity_ids as `sensor.skywatch_<name>` instead of bare
`sensor.<name>` (which collides with everyone else's sightings sensors).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


def build_device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Skywatch",
        manufacturer="ha-skywatch",
        model="Aircraft sightings",
        entry_type=DeviceEntryType.SERVICE,
    )
