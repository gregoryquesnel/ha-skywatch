"""HTTP views — live GeoJSON + Leaflet map page.

Two HomeAssistantViews register on integration setup:

  GET /api/skywatch/flights.geojson
    Returns a GeoJSON FeatureCollection of the currently in-area
    aircraft, decorated with helo / military / watch classification.
    Authenticated — the iframe loads it via the same HA session.

  GET /api/skywatch/map
    Returns the Leaflet map HTML page. The page polls
    /api/skywatch/flights.geojson every 5 s and renders markers.

The map HTML is served from www/skywatch-map.html via
register_static_path. No CDN dependencies are baked into the page in
v0.1 — Leaflet 1.9.4 is loaded from unpkg by default. Self-hosters can
swap the script + stylesheet URLs by editing www/skywatch-map.html
directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.components.http import HomeAssistantView

from .classify import is_helicopter, is_military, match_watch
from .const import (
    CONF_HOME_LATITUDE,
    CONF_HOME_LONGITUDE,
    CONF_RADIUS_KM,
    DEFAULT_RADIUS_KM,
    DOMAIN,
)

if TYPE_CHECKING:
    from aiohttp.web import Request, Response
    from homeassistant.core import HomeAssistant


class SkywatchFlightsGeoJSONView(HomeAssistantView):
    """Live GeoJSON snapshot for the Leaflet map."""

    url = "/api/skywatch/flights.geojson"
    name = "api:skywatch:flights_geojson"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: Request) -> Response:
        coordinators = list(self._hass.data.get(DOMAIN, {}).values())
        if not coordinators:
            return self.json({"type": "FeatureCollection", "features": []})
        coord = coordinators[0]

        flights = coord.source.current_flights()
        features: list[dict] = []
        for f in flights:
            lat = f.get("latitude")
            lon = f.get("longitude")
            if lat is None or lon is None:
                continue
            code = f.get("aircraft_code")
            watch = match_watch(
                {
                    "aircraft_registration": f.get("aircraft_registration"),
                    "aircraft_code": code,
                    "callsign": f.get("callsign"),
                },
                coord.watch_list,
            )
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "flight_id": f.get("id"),
                        "callsign": f.get("callsign"),
                        "altitude_ft": f.get("altitude"),
                        "heading": f.get("heading"),
                        "ground_speed_kt": f.get("ground_speed"),
                        "aircraft_code": code,
                        "aircraft_model": f.get("aircraft_model"),
                        "is_helo": is_helicopter(code, coord.helo_codes),
                        "is_military": is_military(code, coord.military_codes),
                        "watch_slug": watch.slug if watch else None,
                        "watch_label": watch.label if watch else None,
                    },
                }
            )

        config_entry = coord.config_entry
        cfg = {**config_entry.data, **config_entry.options}
        home_lat = float(cfg.get(CONF_HOME_LATITUDE, 0.0))
        home_lon = float(cfg.get(CONF_HOME_LONGITUDE, 0.0))
        radius_km = float(cfg.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM))

        return self.json(
            {
                "type": "FeatureCollection",
                "home": [home_lon, home_lat],
                "radius_m": radius_km * 1000,
                "features": features,
            }
        )


class SkywatchMapView(HomeAssistantView):
    """Static Leaflet page — served from www/skywatch-map.html."""

    url = "/api/skywatch/map"
    name = "api:skywatch:map"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._html_path = Path(__file__).parent.parent.parent / "www" / "skywatch-map.html"

    async def get(self, request: Request) -> Response:
        from aiohttp.web import Response as WebResponse  # noqa: PLC0415

        if not self._html_path.exists():
            return WebResponse(status=404, text="skywatch-map.html missing")
        body = await self._hass.async_add_executor_job(self._html_path.read_text)
        return WebResponse(body=body, content_type="text/html", charset="utf-8")


async def async_register_http_views(hass: HomeAssistant) -> None:
    """Register both views. Safe to call once during setup."""
    hass.http.register_view(SkywatchFlightsGeoJSONView(hass))
    hass.http.register_view(SkywatchMapView(hass))
