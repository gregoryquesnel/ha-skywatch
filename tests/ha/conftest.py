"""HA-fixture conftest.

Only loaded when pytest-homeassistant-custom-component is installed.
Adds the autouse `enable_custom_integrations` fixture so HA can resolve
the skywatch custom_components/ path inside the test harness, and
pre-loads http + websocket_api which skywatch declares as dependencies
in manifest.json (the HA test harness doesn't auto-setup deps).
"""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Force-enable custom integration loading for every test in tests/ha/."""
    yield


@pytest.fixture(autouse=True)
async def setup_http(hass: HomeAssistant):
    """Pre-setup http + websocket_api so skywatch's dep guard is satisfied."""
    await async_setup_component(hass, "http", {})
    await async_setup_component(hass, "websocket_api", {})
