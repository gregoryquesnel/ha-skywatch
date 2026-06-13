"""HTTP API smoke tests against a live HA with skywatch installed.

Skipped unless HA_HOST + HA_TOKEN are set. Run after
  scripts/install-to-ha.sh
  (and after adding the integration via Settings → Devices & Services)
with:
  mise run smoke

These verify the integration loaded, registered its entities, and
serves the live map endpoints. They make ZERO state changes — only
GETs against the HA REST API.
"""
from __future__ import annotations

import os

import pytest
import requests

HA_HOST = os.environ.get("HA_HOST", "10.100.100.200")
HA_PORT = os.environ.get("HA_PORT", "8123")
HA_TOKEN = os.environ.get("HA_TOKEN")
BASE = f"http://{HA_HOST}:{HA_PORT}"

pytestmark = pytest.mark.skipif(
    not HA_TOKEN, reason="HA_TOKEN env var not set"
)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }


@pytest.fixture
def state_of():
    """Returns a fetch-state function for any entity_id."""

    def fetch(entity_id: str) -> dict:
        resp = requests.get(
            f"{BASE}/api/states/{entity_id}", headers=_headers(), timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    return fetch


@pytest.mark.parametrize(
    "entity_id",
    [
        "sensor.skywatch_log_today",
        "sensor.skywatch_log_this_week",
        "sensor.skywatch_log_stats",
        "sensor.skywatch_log_recent",
        "sensor.skywatch_log_overhead",
        "sensor.skywatch_movements_today",
        "sensor.skywatch_flights_in_area",
        "binary_sensor.skywatch_has_aircraft",
        "binary_sensor.skywatch_helicopter_overhead",
    ],
)
def test_entity_exists(state_of, entity_id: str) -> None:
    """Every core skywatch entity should be registered."""
    state = state_of(entity_id)
    assert state["entity_id"] == entity_id
    assert state["state"] not in ("unavailable", None)


def test_log_today_is_numeric(state_of) -> None:
    state = state_of("sensor.skywatch_log_today")
    assert state["state"].isdigit(), f"unexpected state: {state['state']}"


def test_log_recent_has_pagination_attrs(state_of) -> None:
    state = state_of("sensor.skywatch_log_recent")
    attrs = state["attributes"]
    for key in ("page", "total_pages", "page_size", "total_count"):
        assert key in attrs, f"missing pagination key: {key}"


def test_log_stats_has_top_airlines(state_of) -> None:
    state = state_of("sensor.skywatch_log_stats")
    assert "top_airlines" in state["attributes"]
    assert isinstance(state["attributes"]["top_airlines"], list)


def test_flights_geojson_endpoint() -> None:
    """Live map JSON endpoint should return a FeatureCollection."""
    resp = requests.get(
        f"{BASE}/api/skywatch/flights.geojson", headers=_headers(), timeout=10
    )
    resp.raise_for_status()
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert "features" in data
    assert isinstance(data["features"], list)


def test_flights_geojson_has_home_and_radius() -> None:
    resp = requests.get(
        f"{BASE}/api/skywatch/flights.geojson", headers=_headers(), timeout=10
    )
    data = resp.json()
    # Both keys appear when at least one coordinator is set up.
    if data["features"] or "home" in data:
        assert "home" in data
        assert "radius_m" in data
        assert isinstance(data["home"], list)
        assert len(data["home"]) == 2


def test_map_endpoint_serves_html() -> None:
    resp = requests.get(
        f"{BASE}/api/skywatch/map", headers=_headers(), timeout=10
    )
    resp.raise_for_status()
    assert "text/html" in resp.headers.get("Content-Type", "")
    body = resp.text
    # Smoke check that the Leaflet page contents are intact.
    assert "leaflet" in body.lower()
    assert "/api/skywatch/flights.geojson" in body
