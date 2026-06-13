"""Skywatch HA services.

Thin wrapper around the pure-Python legacy_import module. The handler
opens a sync sqlite3 connection in an executor thread, runs the import
transactionally, and writes a `.legacy_imported` sentinel on success.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DB_FILENAME, DB_SUBDIR, DOMAIN
from .legacy_import import LegacyImportError, import_legacy_db

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


_LOGGER = logging.getLogger(__name__)

SERVICE_IMPORT_LEGACY_DB = "import_legacy_db"

IMPORT_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("source_path", default="/config/sky_sightings.db"): cv.string,
    }
)


async def async_register_services(hass: HomeAssistant) -> None:
    """Register skywatch.* services. Called once during integration setup."""

    async def _handle_import_legacy(call: ServiceCall) -> None:
        source_path = Path(call.data.get("source_path", "/config/sky_sightings.db"))

        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise HomeAssistantError("Skywatch is not configured.")
        target_db_path = Path(hass.config.path(DB_SUBDIR)) / DB_FILENAME

        def _do_import() -> dict:
            conn = sqlite3.connect(target_db_path)
            try:
                summary = import_legacy_db(conn, source_path)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                conn.close()
            return summary

        try:
            summary = await hass.async_add_executor_job(_do_import)
        except LegacyImportError as err:
            raise HomeAssistantError(str(err)) from err

        _LOGGER.info("Skywatch legacy import complete from %s: %s", source_path, summary)

        sentinel = target_db_path.parent / ".legacy_imported"
        await hass.async_add_executor_job(
            lambda: sentinel.write_text(f"imported from {source_path}\n")
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_LEGACY_DB,
        _handle_import_legacy,
        schema=IMPORT_SERVICE_SCHEMA,
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    hass.services.async_remove(DOMAIN, SERVICE_IMPORT_LEGACY_DB)
