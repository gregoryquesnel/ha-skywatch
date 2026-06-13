"""Config flow without OptionsFlow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow

from .const import (
    CONF_AIRPORT_IATA,
    CONF_HOME_LATITUDE,
    CONF_HOME_LONGITUDE,
    CONF_RADIUS_KM,
    CONF_SOURCE,
    DEFAULT_RADIUS_KM,
    DOMAIN,
    SOURCE_FR24,
)

FR24_DOMAIN = "flightradar24"
SINGLETON_UNIQUE_ID = "skywatch_singleton"


class SkywatchConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

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
                await self.async_set_unique_id(SINGLETON_UNIQUE_ID)
                self._abort_if_unique_id_configured()
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
                    vol.Required(CONF_HOME_LATITUDE, default=default_lat): vol.Coerce(float),
                    vol.Required(CONF_HOME_LONGITUDE, default=default_lon): vol.Coerce(float),
                    vol.Optional(CONF_AIRPORT_IATA, default=""): str,
                    vol.Required(CONF_RADIUS_KM, default=DEFAULT_RADIUS_KM): vol.Coerce(int),
                }
            ),
            errors=errors,
        )
