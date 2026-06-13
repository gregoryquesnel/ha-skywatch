"""Skywatch constants."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "skywatch"

CONF_HOME_LATITUDE: Final = "home_latitude"
CONF_HOME_LONGITUDE: Final = "home_longitude"
CONF_AIRPORT_IATA: Final = "airport_iata"
CONF_RADIUS_KM: Final = "radius_km"
CONF_SOURCE: Final = "source"
CONF_WATCH_LIST: Final = "watch_list"
CONF_HELO_CODES: Final = "helo_codes"
CONF_MILITARY_CODES: Final = "military_codes"
CONF_ALERTS_ENABLED: Final = "alerts_enabled"
CONF_QUIET_HOURS_START: Final = "quiet_hours_start"
CONF_QUIET_HOURS_END: Final = "quiet_hours_end"

SOURCE_FR24: Final = "fr24"

DEFAULT_RADIUS_KM: Final = 50
DEFAULT_OVERHEAD_DISTANCE_KM: Final = 5
DEFAULT_OVERHEAD_ALTITUDE_FT: Final = 10000
DEFAULT_ENTRY_TTL_HOURS: Final = 2

DB_FILENAME: Final = "sightings.db"
DB_SUBDIR: Final = "skywatch"

SCHEMA_VERSION: Final = 1

EVENT_SKYWATCH_SIGHTING: Final = "skywatch_sighting"
EVENT_SKYWATCH_WATCH_MATCH: Final = "skywatch_watch_match"

DEFAULT_HELO_CODES: Final = (
    "A002", "A109", "A119", "A129", "A139", "A149", "A169", "A189",
    "ALH", "ALO2", "ALO3", "AS32", "AS3B", "AS50", "AS55", "AS65",
    "B06", "B06T", "B105", "B212", "B222", "B230", "B407", "B412",
    "B427", "B429", "B430", "B47G", "B47J", "BK17", "BSTP",
    "EC20", "EC25", "EC30", "EC35", "EC45", "EC55", "EC75",
    "EH10", "EXPL", "FREL", "GAZL",
    "H2", "H269", "H47", "H500", "H53", "H53S", "H60", "H64", "HUCO",
    "KA32", "KA50", "KA52", "KMAX",
    "LAMA", "LYNX", "MI26", "MI38", "MI8", "NH90", "OH1",
    "PUMA", "R22", "R44", "R66", "RVAL",
    "S61", "S61R", "S76", "S92", "SUCO", "TIGR",
    "UH1", "UH1Y", "V22", "B505", "G2CA", "GYRO", "H160", "CDUS", "MM24",
)

DEFAULT_MILITARY_CODES: Final = (
    "C130", "C30J", "CC30",
    "K35R", "KC35", "KC10", "KC30", "KC46",
    "C17", "C5", "C5M",
    "C40", "C32", "C20", "C21",
    "P3", "P8", "CP14", "CT44",
    "F15", "F16", "F18", "F22", "F35", "FA18", "A10", "A4",
    "B1", "B2", "B52", "B58",
    "U2", "U28", "RC35", "E3CF", "E3TF", "E4",
    "RQ4", "RQ7", "MQ1", "MQ9",
    "T6", "T38", "T44", "T45", "T1", "T2",
    "AN12", "AN22", "AN70", "IL76", "IL96", "TU16", "TU22", "TU95",
)
