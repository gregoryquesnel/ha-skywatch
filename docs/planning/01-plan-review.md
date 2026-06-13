# Plan Review (Adversarial)

> Produced by a `Plan`-agent code review of the initial ha-skywatch plan, 2026-06-13. Preserved verbatim as a reference of the risks identified before implementation began.

## HIGH severity

### H1. The `command_line` → entity-attributes pattern doesn't survive translation

The current dashboards consume **rows-as-attributes** (`sightings: [...]` lists up to 50 items, plus `buckets`, `top_routes`, etc.). HA's design rules say state-bearing attributes should be small, immutable-ish scalars; large list attributes blow up the state machine (the existing install already worked around this with recorder excludes). If you replicate that shape in `SensorEntity`, you inherit every problem you currently exclude from recorder — plus the new HA core check that warns/strips attributes over 16 KB in newer cores, plus the recorder-history payload bloat for every state change.

**Mitigation:** Don't port the query sensors as SensorEntities. Expose them as HA **WebSocket commands** (`websocket_api.async_register_command`) returning JSON to a custom card, or as **REST views** the card fetches directly. Keep only true scalars as sensors: `sensor.skywatch_today_count`, `sensor.skywatch_overhead_count`, `binary_sensor.skywatch_aircraft_present`. The card calls `skywatch/sightings/recent?page=2` over WS. This is the same pattern `history` and `logbook` use.

### H2. Backend abstraction will leak FR24-specific semantics

FR24's HA integration is event-driven (`flightradar24_entry`/`exit`/`area_landed`/`area_took_off`) AND state-bearing (`sensor.flightradar24_current_in_area.attributes.flights`). Your insert script consumes events; your GeoJSON renderer consumes the flights attribute. Any non-FR24 backend (dump1090 JSON polling, tar1090, ADSB-Hub) is poll-based, gives raw position frames at 1 Hz, has no concept of "entry/exit," and exposes registration/callsign but rarely airline/origin/destination. Your schema (`origin_city`, `airline_iata`, `aircraft_photo`) is shaped entirely by FR24.

**Mitigation:** Don't ship a multi-backend abstraction in v0.1. Pick the **right boundary** instead: a normalized internal model `Sighting{flight_id, callsign, registration, model, code, first_seen, last_seen, closest_km, lat/lon/alt at closest}` plus an **adapter contract** that takes raw frames and emits `entry`/`exit`/`update` events. Then ship only the FR24 adapter. Document the adapter contract; let community PRs fill in dump1090. Calling the v0.1 "backend pluggable" when only one exists is the trap — pick a name like `source: fr24` in the config flow and reserve the key.

### H3. HACS does NOT support a single repo bundling an integration + card cleanly

HACS' validation distinguishes `integration` repos and `plugin` (Lovelace card) repos by the presence of `hacs.json`/`manifest.json` at specific paths and by the **category** field in the HACS default list. A user adds your repo once with **one category**. You cannot install both halves from a single custom repo entry in current HACS (multi-category repos aren't supported; the `content_in_root` + category combo only lets you ship one type).

**Mitigation:** Two repos: `ha-skywatch` (integration) and `ha-skywatch-card` (Lovelace plugin). The integration can `register_static_path` to serve a bundled copy of the Leaflet HTML/JS without going through HACS' plugin pipeline — that part can stay in the integration repo. The custom card (`skywatch-map-card` as a true Lovelace element) goes in the second repo.

### H4. Migration path for the existing 1000s-of-rows DB needs explicit ownership

Your current DB is at `/config/sky_sightings.db`. Moving it to (probably) `/config/.storage/skywatch/sightings.db` or `/config/skywatch/sightings.db` means the user's first install of v0.1 finds an empty DB unless you migrate. ALTER TABLE migrations on an unknown-schema legacy file are landmines — you've already accumulated 3 add-column migrations + an idempotent data-cleanup UPDATE for the `https:https://` bug.

**Mitigation:** Ship a one-shot migration service `skywatch.import_legacy_db` that takes `source_path` (default `/config/sky_sightings.db`), runs schema introspection, copies rows into the new DB applying current schema, and writes a `.migrated` sentinel. Don't auto-run on startup — fail-loud is better than silently dropping a column. Document this in the README as Step 1 for upgraders.

## MEDIUM severity

### M1. SQLite location: don't use `.storage/`

`hass.config.path(".storage/...")` is **reserved for HA core's entity/config registry JSON**. Third parties putting binary databases there violates the convention and risks future HA cleanup logic. Use `hass.config.path("skywatch/sightings.db")` (a top-level subdir) — same place Frigate, Plex, and most file-writing integrations land.

### M2. Recorder load — your integration adds it back

You currently exclude command_line sensors from recorder. New entity-shaped sensors will be recorded by default. Even pure scalar count sensors generate state changes on every FR24 scan.

**Mitigation:** Set `entity_category=DIAGNOSTIC` on the noisy/large-attribute ones, OR document a `recorder.exclude` snippet in the README. For attributes you do want available but not recorded, use `extra_state_attributes` and document the exclude.

### M3. Schema versioning — your gotcha is the `entry_time` NULL semantic

Your migration adds `entry_time` as a nullable column, then `query_rows` computes `dwell_seconds = None` for rows that pre-date the entry-capture automation. New users will never have NULL `entry_time` on new rows but **will if you import a legacy DB** (H4). The card must render `dwell: —` gracefully. Don't backfill NULLs with fake values; surface "unknown" explicitly.

Also: use a real migration framework. `CREATE TABLE IF NOT EXISTS` + ad-hoc ALTERs is what you have today, and it's already brittle. Use a `schema_version` PRAGMA (`PRAGMA user_version`) + a list of forward-only migration functions.

### M4. FR24 dependency declaration

`manifest.json` has no way to declare a HACS-integration dependency. The `dependencies` field is for **HA core components only** (e.g. `http`, `frontend`). You cannot declare `flightradar24` as required.

**Mitigation:** Strict-runtime check: in `async_setup_entry`, look up the FR24 config entry; if missing, raise `ConfigEntryNotReady` with a helpful message. Document prominently in README. For v0.1, **strict requirement** — don't make it optional yet.

### M5. Custom card name `skywatch-map-card` may collide

There's no central registry but the term "skywatch" overlaps with several iOS apps and at least one ADSB project. Domain `skywatch` itself may already exist — verify against [github.com/hacs/default](https://github.com/hacs/default/blob/main/integration) before committing to the name.

### M6. Drop Regina-specific data from the package

YQR, C-GRPF, "America/Regina", the 84-code helo allowlist, military ICAO list — these all need to either become **config-flow options** or **distribution-config files**. The Jinja macros `helo_codes()`/`is_regina_police_unit()` are an anti-pattern for distribution. Replace with a **template entity** the integration registers, or a **service** `skywatch.classify_flight` that returns the category.

## LOW severity

### L1. v0.1 scope cuts — be ruthless
Cut from v0.1: the histogram, top-routes, this-week template sensor, military view, police-air alert (Regina-specific), the GeoJSON pipeline. Ship: capture (entry/exit only — drop area_landed/took_off), today/recent/search queries, Leaflet map via static path, one scalar `aircraft_present` binary sensor, one alert blueprint.

### L2. Blueprints in an integration repo
Blueprints aren't installed by the integration — they go in `blueprints/automation/skywatch/` and HACS picks them up via the integration's `hacs.json` `zip_release: false` + manual user import.

### L3. HACS manifest landmines
- `manifest.json` requires `version` for custom integrations.
- `iot_class` is required and validated: yours is `cloud_polling` (FR24 is cloud).
- `integration_type: "service"` is appropriate.
- `dependencies: ["http"]` needed for `register_static_path`.
- `hacs.json` should set `"homeassistant": "2024.6.0"` (or whatever your minimum).

### L4. The Leaflet map's CDN dependencies
`unpkg.com/leaflet@1.9.4` is fine for personal use, terrible for distribution. Bundle Leaflet via your static path. ~150 KB minified.
