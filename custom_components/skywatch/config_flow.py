"""Skywatch config + options flows.

Initial setup is a single step: home lat/lon (defaulted from HA's
configured location), local airport IATA, and watch radius. Source is
hardcoded to FR24 for v0.1 — the config-flow key is reserved so a future
source can land without entry-shape migration.

Options flow lets the user edit the watch list (one row per watched
aircraft), the helo / military ICAO code lists, and the overhead-
threshold parameters.

Singleton: only one Skywatch config entry per HA install. Multi-airport
support would mean multiple coordinators with distinct DB paths — not
in v0.1 scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_AIRPORT_IATA,
    CONF_HELO_CODES,
    CONF_HOME_LATITUDE,
    CONF_HOME_LONGITUDE,
    CONF_MILITARY_CODES,
    CONF_OVERHEAD_ALTITUDE_FT,
    CONF_OVERHEAD_DISTANCE_KM,
    CONF_RADIUS_KM,
    CONF_SOURCE,
    CONF_WATCH_LIST,
    DEFAULT_HELO_CODES,
    DEFAULT_MILITARY_CODES,
    DEFAULT_OVERHEAD_ALTITUDE_FT,
    DEFAULT_OVERHEAD_DISTANCE_KM,
    DEFAULT_RADIUS_KM,
    DOMAIN,
    SOURCE_FR24,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


FR24_DOMAIN = "flightradar24"

SINGLETON_UNIQUE_ID = "skywatch_singleton"


def _validate_watch_entry(item: Any) -> dict:
    """Coerce a watch-list options input into a normalized dict.

    Raises vol.Invalid on missing slug. Other fields are forgiving.
    """
    if not isinstance(item, dict):
        raise vol.Invalid("each watch list entry must be a dict")
    slug = item.get("slug")
    if not slug or not isinstance(slug, str):
        raise vol.Invalid("watch list entry missing required 'slug' field")
    return {
        "slug": slug,
        "label": item.get("label") or slug,
        "registration": item.get("registration") or None,
        "aircraft_code": item.get("aircraft_code") or None,
        "match_blocked": bool(item.get("match_blocked", False)),
    }


class SkywatchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial config flow — collect home location + airport."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        await self.async_set_unique_id(SINGLETON_UNIQUE_ID)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            lat = user_input.get(CONF_HOME_LATITUDE)
            lon = user_input.get(CONF_HOME_LONGITUDE)
            iata = (user_input.get(CONF_AIRPORT_IATA) or "").strip().upper()
            radius = user_input.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM)

            if lat is None or not -90 <= float(lat) <= 90:
                errors["base"] = "invalid_latitude"
            elif lon is None or not -180 <= float(lon) <= 180:
                errors["base"] = "invalid_longitude"
            elif iata and (len(iata) != 3 or not iata.isalpha()):
                errors["base"] = "invalid_iata"
            elif not self.hass.config_entries.async_entries(FR24_DOMAIN):
                errors["base"] = "fr24_not_loaded"

            if not errors:
                return self.async_create_entry(
                    title="Skywatch",
                    data={
                        CONF_HOME_LATITUDE: float(lat),
                        CONF_HOME_LONGITUDE: float(lon),
                        CONF_AIRPORT_IATA: iata or None,
                        CONF_RADIUS_KM: int(radius),
                        CONF_SOURCE: SOURCE_FR24,
                    },
                )

        default_lat = self.hass.config.latitude
        default_lon = self.hass.config.longitude

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOME_LATITUDE, default=default_lat): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=-90, max=90, step=0.000001, mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(CONF_HOME_LONGITUDE, default=default_lon): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=-180, max=180, step=0.000001, mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                    vol.Optional(CONF_AIRPORT_IATA, default=""): selector.TextSelector(),
                    vol.Required(
                        CONF_RADIUS_KM, default=DEFAULT_RADIUS_KM
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1, max=500, step=1, mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SkywatchOptionsFlow()


class SkywatchOptionsFlow(OptionsFlow):
    """Options flow — watch list, helo / military codes, overhead thresholds."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                watch_list = [
                    _validate_watch_entry(item) for item in (user_input.get(CONF_WATCH_LIST) or [])
                ]
            except vol.Invalid:
                errors["base"] = "invalid_watch_list"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_WATCH_LIST: watch_list,
                        CONF_HELO_CODES: user_input.get(CONF_HELO_CODES)
                        or list(DEFAULT_HELO_CODES),
                        CONF_MILITARY_CODES: user_input.get(CONF_MILITARY_CODES)
                        or list(DEFAULT_MILITARY_CODES),
                        CONF_OVERHEAD_DISTANCE_KM: float(
                            user_input.get(CONF_OVERHEAD_DISTANCE_KM, DEFAULT_OVERHEAD_DISTANCE_KM)
                        ),
                        CONF_OVERHEAD_ALTITUDE_FT: int(
                            user_input.get(CONF_OVERHEAD_ALTITUDE_FT, DEFAULT_OVERHEAD_ALTITUDE_FT)
                        ),
                    },
                )

        current = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_WATCH_LIST,
                        default=current.get(CONF_WATCH_LIST, []),
                    ): selector.ObjectSelector(),
                    vol.Optional(
                        CONF_HELO_CODES,
                        default=current.get(CONF_HELO_CODES, list(DEFAULT_HELO_CODES)),
                    ): selector.ObjectSelector(),
                    vol.Optional(
                        CONF_MILITARY_CODES,
                        default=current.get(CONF_MILITARY_CODES, list(DEFAULT_MILITARY_CODES)),
                    ): selector.ObjectSelector(),
                    vol.Optional(
                        CONF_OVERHEAD_DISTANCE_KM,
                        default=current.get(
                            CONF_OVERHEAD_DISTANCE_KM, DEFAULT_OVERHEAD_DISTANCE_KM
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.1,
                            max=50.0,
                            step=0.1,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_OVERHEAD_ALTITUDE_FT,
                        default=current.get(
                            CONF_OVERHEAD_ALTITUDE_FT, DEFAULT_OVERHEAD_ALTITUDE_FT
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1000,
                            max=50000,
                            step=500,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
            errors=errors,
        )
