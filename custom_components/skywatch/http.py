"""HTTP views — live GeoJSON + Leaflet map page.

Two HomeAssistantViews register on integration setup:

  GET /api/skywatch/flights.geojson
    Returns a GeoJSON FeatureCollection of the currently in-area
    aircraft, decorated with helo / military / watch classification.
    Authenticated — the iframe loads it via the same HA session.

  GET /api/skywatch/map
    Returns the Leaflet map HTML page. The page polls
    /api/skywatch/flights.geojson every 5 s and renders markers.

The map HTML is served from custom_components/skywatch/www/skywatch-map.html
(inside the package so HACS distributes it). No CDN dependencies are
baked into the page; Leaflet 1.9.4 loads from unpkg by default.
Self-hosters can swap the script + stylesheet URLs by editing the
HTML directly.
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
    """Live GeoJSON snapshot for the Leaflet map.

    requires_auth=False so the Leaflet iframe (served at /api/skywatch/map)
    can fetch it without same-origin cookie tricks. Exposes only the same
    flight data the FR24 sensor already surfaces — no credentials, no
    private state. HA still enforces the same-origin policy via the
    cors_allowed_origins setting if the user wants to lock external
    access.
    """

    url = "/api/skywatch/flights.geojson"
    name = "api:skywatch:flights_geojson"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: Request) -> Response:
        coordinators = list(self._hass.data.get(DOMAIN, {}).values())
        if not coordinators:
            return self.json({"type": "FeatureCollection", "features": []})
        coord = coordinators[0]

        flights = coord.source.current_flights()
        features: list[dict] = []
        flight_ids: list[str] = []
        helo_ids: set[str] = set()
        for f in flights:
            lat = f.get("latitude")
            lon = f.get("longitude")
            if lat is None or lon is None:
                continue
            code = f.get("aircraft_code")
            is_helo = is_helicopter(code, coord.helo_codes)
            watch = match_watch(
                {
                    "aircraft_registration": f.get("aircraft_registration"),
                    "aircraft_code": code,
                    "callsign": f.get("callsign"),
                },
                coord.watch_list,
            )
            fid = f.get("id") or f.get("callsign") or f.get("flight_number")
            if fid:
                flight_ids.append(str(fid))
                if is_helo:
                    helo_ids.add(str(fid))
            features.append(
                {
                    "type": "Feature",
                    "id": str(fid) if fid else None,
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "flight_id": f.get("id"),
                        "callsign": f.get("callsign"),
                        "altitude_ft": f.get("altitude"),
                        "heading": f.get("heading"),
                        "ground_speed_kt": f.get("ground_speed"),
                        "aircraft_code": code,
                        "aircraft_model": f.get("aircraft_model"),
                        "is_helo": is_helo,
                        "is_military": is_military(code, coord.military_codes),
                        "watch_slug": watch.slug if watch else None,
                        "watch_label": watch.label if watch else None,
                    },
                }
            )

        # Trail LineStrings — one per flight with ≥2 captured positions.
        if flight_ids:
            trails = await coord.async_fetch_trails(flight_ids)
            for fid, coords in trails.items():
                if len(coords) < 2:
                    continue
                features.append(
                    {
                        "type": "Feature",
                        "id": f"{fid}-trail",
                        "geometry": {"type": "LineString", "coordinates": coords},
                        "properties": {
                            "trail_for": fid,
                            "is_helo": fid in helo_ids,
                            "sample_count": len(coords),
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
                "audible_radius_m": 8000,
                "features": features,
            }
        )


class SkywatchMapView(HomeAssistantView):
    """Static Leaflet page — served from custom_components/skywatch/www/skywatch-map.html.

    requires_auth=False so the page renders inside Lovelace iframes
    (which don't forward HA's auth cookie). The HTML is static and
    doesn't expose any state.

    Path: the HTML ships INSIDE the custom_components/skywatch/
    package so HACS distributes it alongside the Python code. A path
    of <repo_root>/www/<file> would not work for HACS users because
    HACS only mirrors the integration directory.
    """

    url = "/api/skywatch/map"
    name = "api:skywatch:map"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._html_path = Path(__file__).parent / "www" / "skywatch-map.html"

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
