"""Skywatch integration setup.

`async_setup_entry` instantiates the Fr24Source, builds the
SkywatchCoordinator, and forwards the config entry to the sensor +
binary_sensor platforms. `async_unload_entry` reverses that.

Options-flow changes trigger a full integration reload (simplest correct
behaviour — watch lists, helo codes, and quiet hours all bake into
coordinator state at startup).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from .classify import WatchEntry
from .const import (
    CONF_HELO_CODES,
    CONF_MILITARY_CODES,
    CONF_OVERHEAD_ALTITUDE_FT,
    CONF_OVERHEAD_DISTANCE_KM,
    CONF_TIMEZONE,
    CONF_WATCH_LIST,
    DEFAULT_HELO_CODES,
    DEFAULT_MILITARY_CODES,
    DEFAULT_OVERHEAD_ALTITUDE_FT,
    DEFAULT_OVERHEAD_DISTANCE_KM,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

# HA platform names. Using strings rather than the Platform enum keeps
# the package importable without homeassistant installed — pure-Python
# unit tests for storage / classify / data_builder traverse this module
# during pytest collection.
PLATFORMS: list[str] = [
    "sensor",
    "binary_sensor",
    "number",
    "text",
    "switch",
    "button",
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Skywatch from a config entry."""
    # Lazy imports — see PLATFORMS comment above.
    from .backends import Fr24Source  # noqa: PLC0415
    from .coordinator import SkywatchCoordinator  # noqa: PLC0415

    hass.data.setdefault(DOMAIN, {})

    cfg = {**entry.data, **entry.options}

    tz_name = cfg.get(CONF_TIMEZONE) or hass.config.time_zone or "UTC"
    tz = ZoneInfo(tz_name)

    helo_codes = tuple(cfg.get(CONF_HELO_CODES) or DEFAULT_HELO_CODES)
    military_codes = tuple(cfg.get(CONF_MILITARY_CODES) or DEFAULT_MILITARY_CODES)
    watch_list = tuple(WatchEntry.from_dict(item) for item in (cfg.get(CONF_WATCH_LIST) or []))
    overhead_distance_km = float(cfg.get(CONF_OVERHEAD_DISTANCE_KM, DEFAULT_OVERHEAD_DISTANCE_KM))
    overhead_altitude_ft = int(cfg.get(CONF_OVERHEAD_ALTITUDE_FT, DEFAULT_OVERHEAD_ALTITUDE_FT))

    source = Fr24Source(hass)
    coordinator = SkywatchCoordinator(
        hass,
        entry,
        source,
        tz=tz,
        helo_codes=helo_codes,
        military_codes=military_codes,
        watch_list=watch_list,
        overhead_distance_km=overhead_distance_km,
        overhead_altitude_ft=overhead_altitude_ft,
    )

    await coordinator.async_setup()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register skywatch.* services + HTTP views on first entry only;
    # both are removed on last-unload below.
    if len(hass.config_entries.async_entries(DOMAIN)) == 1:
        from .http import async_register_http_views  # noqa: PLC0415
        from .services import async_register_services  # noqa: PLC0415

        await async_register_services(hass)
        await async_register_http_views(hass)

    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options_change))
    return True


async def _async_reload_on_options_change(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_unload()
        if not hass.config_entries.async_entries(DOMAIN):
            from .services import async_unregister_services  # noqa: PLC0415

            async_unregister_services(hass)
    return unload_ok
