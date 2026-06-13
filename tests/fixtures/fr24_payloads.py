"""Canonical FR24 event payload fixtures.

Hand-crafted to mirror real Flightradar24 HACS integration events. Used
by backend translation tests and (later) coordinator integration tests.
"""

from __future__ import annotations

from typing import Final

ENTRY_PAYLOAD: Final[dict] = {
    "id": "flight_abc123",
    "callsign": "ACA123",
    "flight_number": "AC123",
    "aircraft_code": "B738",
    "aircraft_model": "Boeing 737-8 MAX",
    "aircraft_registration": "C-FGAR",
    "airline": "Air Canada",
    "airline_iata": "AC",
    "airport_origin_code_iata": "YYC",
    "airport_origin_city": "Calgary",
    "airport_destination_code_iata": "YVR",
    "airport_destination_city": "Vancouver",
    "altitude": 10500,
    "ground_speed": 450,
    "heading": 270,
    "vertical_speed": 1200,
    "closest_distance": 3.5,
    "aircraft_photo_small": "https://cdn.jetphotos.com/200/photo.jpg",
    "tracked_by_device": "dev_123",
}

EXIT_PAYLOAD: Final[dict] = {
    **ENTRY_PAYLOAD,
    "closest_distance": 3.2,
    "altitude": 12000,
}

# An exit payload with the legacy 'https:https://' doubled-prefix bug.
EXIT_PAYLOAD_WITH_DOUBLED_PHOTO: Final[dict] = {
    **EXIT_PAYLOAD,
    "aircraft_photo_small": "https:https://cdn.jetphotos.com/200/photo.jpg",
}

# Privacy-blocked: Regina Police Air Unit (C-GRPF) — registration nulled,
# callsign = literal "Blocked". This is the fingerprint pattern the
# watch-list adapter must still match.
BLOCKED_EXIT_PAYLOAD: Final[dict] = {
    "id": "flight_blocked",
    "callsign": "Blocked",
    "flight_number": None,
    "aircraft_code": "C182",
    "aircraft_model": "Cessna 182T Skylane",
    "aircraft_registration": None,
    "airline": None,
    "airline_iata": None,
    "airport_origin_code_iata": None,
    "airport_origin_city": None,
    "airport_destination_code_iata": None,
    "airport_destination_city": None,
    "altitude": 3500,
    "ground_speed": 80,
    "heading": 90,
    "vertical_speed": 0,
    "closest_distance": 2.4,
    "aircraft_photo_small": None,
    "tracked_by_device": "dev_123",
}

LANDED_PAYLOAD: Final[dict] = {
    "id": "flight_land1",
    "callsign": "WJA802",
    "flight_number": "WS802",
    "aircraft_code": "B737",
    "aircraft_model": "Boeing 737-700",
    "aircraft_registration": "C-GWSX",
    "airline": "WestJet",
    "airline_iata": "WS",
    "airport_origin_code_iata": "YYC",
    "airport_destination_code_iata": "YQR",
    "aircraft_photo_small": "https://cdn.jetphotos.com/200/p.jpg",
}

TOOK_OFF_PAYLOAD: Final[dict] = {
    "id": "flight_to1",
    "callsign": "WJA803",
    "flight_number": "WS803",
    "aircraft_code": "B737",
    "aircraft_model": "Boeing 737-700",
    "aircraft_registration": "C-GWSX",
    "airline": "WestJet",
    "airline_iata": "WS",
    "airport_origin_code_iata": "YQR",
    "airport_destination_code_iata": "YYC",
    "aircraft_photo_small": "https://cdn.jetphotos.com/200/q.jpg",
}

MALFORMED_PAYLOAD: Final[dict] = {
    # missing "id" — should yield None from translators
    "callsign": "ABC123",
}
