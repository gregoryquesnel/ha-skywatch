# Skywatch

Home Assistant aircraft sightings, watch lists, and overhead alerts — persisted to a local SQLite log, surfaced as sensors, with configurable per-aircraft watch entries.

> Status: **pre-release scaffold**. The integration does not yet load; manifest is reserved and storage / coordinator / platforms are being built incrementally. See [`docs/planning/`](docs/planning/) for the spec.

## What it does

- Captures every aircraft that transits a configurable radius around your home (default 50 km).
- Persists each sighting to `<config>/skywatch/sightings.db` (separate from the recorder DB).
- Surfaces queryable sensors: recent sightings, today/this week counts, top routes, hour-of-day histogram, military / helicopter / overhead subsets, airport movements.
- Watch list: alert when a specific aircraft (by registration / callsign / pattern) enters the area.
- Backend-agnostic: ships an adapter for the [Flightradar24 HACS integration](https://github.com/AlexandrErohin/home-assistant-flightradar24) for v0.1; the source-adapter interface allows future backends (dump1090 / tar1090 / ADSB-Hub).

## Status

This is a v0.0.x scaffold being built up incrementally. The phased plan, planning artifacts, and test strategy live under [`docs/planning/`](docs/planning/).

## Dependencies (planned)

- **Required:** HACS integration `flightradar24` ([AlexandrErohin/home-assistant-flightradar24](https://github.com/AlexandrErohin/home-assistant-flightradar24)) — Skywatch consumes its events.
- **Recommended for dashboards:** HACS card `flightradar-flight-card` ([plckr/flightradar-flight-card](https://github.com/plckr/flightradar-flight-card)).

## Roadmap

- v0.1 — FR24 adapter, sightings DB + sensors, watch list, alerts blueprint, parameterized Leaflet map via `register_static_path`, example dashboard YAML.
- v0.2+ — Native custom card (split repo), additional backends (dump1090 / tar1090), multi-airport.

## License

MIT — see [`LICENSE`](LICENSE).
