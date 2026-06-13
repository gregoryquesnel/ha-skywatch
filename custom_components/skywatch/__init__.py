"""Skywatch integration scaffold.

Implementation is built up across coordinator / storage / backends / platforms
in subsequent commits. Setup currently returns False so HA refuses to load the
integration before the implementation lands — preventing a half-wired install
from creating partial entities that would have to be cleaned up.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.warning(
        "Skywatch integration is not yet implemented (domain=%s). "
        "Setup refuses until the build lands.",
        DOMAIN,
    )
    return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
