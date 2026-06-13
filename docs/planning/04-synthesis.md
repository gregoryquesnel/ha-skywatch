# v0.1 Implementation Synthesis

> Reconciles the three planning docs (plan review, test strategy, code inventory) into the v0.1 implementation contract. Read this first; the others are reference.

## Repo identity

- **Repo:** `/home/gq/git/ha-skywatch/` (local-only until user review; not pushed)
- **Integration domain:** `skywatch`
- **License:** MIT (`Gregoy Quesnel`, 2026)
- **Provisional name:** "Skywatch" — pending HACS-default-repo collision check before push (tracked as task #14).

## Scope decisions

### What ships in v0.1

The reviewer counseled aggressive cuts; the user counseled "the full sky tab, generalized." The compromise: ship every existing feature, but generalize the install-specific bits behind config. v0.1 surface area:

- 12 sensors (recent / today / search / stats / top_routes / overhead / hour_histogram / military / movements_today / per-watch / this_week / flights_geojson)
- 2 binary sensors (has_aircraft, helicopter_overhead)
- 4 input_* helpers — *not built into the integration*; documented as standard HA core inputs the user creates themselves. (Reason: built-in inputs would require platform support for input_text / input_number which is HA-core-only; not worth re-implementing.)
- 1 service (`skywatch.import_legacy_db`)
- 3 blueprints (entry-alert, watch-list-match, daily-digest)
- 1 example dashboard YAML
- Leaflet map served via `register_static_path` (parameterized, no Regina hardcoding)
- FR24 source adapter; reserved `source: fr24` key in config flow for future backends

### What's explicitly out of scope for v0.1

- Native custom Lovelace card. Leaflet via static path covers the visualization need; a true custom card waits for v0.2 and a split repo (per H3 of the plan review).
- A second backend (dump1090, tar1090, ADSB-Hub). The adapter contract is defined; only FR24 is implemented.
- Auto-import of legacy DB. Manual `skywatch.import_legacy_db` service only — fail-loud is better than silent partial migrations (per H4).
- Down-migrations of the SQLite schema. Users on old versions restore from backup (documented in README).

## Architectural calls

### Storage (M3, M1)

- Path: `<config>/skywatch/sightings.db` — top-level dir, **not** `.storage/` (which HA reserves for core registries).
- Migration ladder: forward-only via `PRAGMA user_version`. Starting schema = baseline v1 that already includes the indexes the legacy schema is missing (`aircraft_code`, `altitude_ft`, `closest_km`, `origin_iata`, `destination_iata`, and an `on_ground` boolean column).
- `entry_time` is nullable; the renderer surfaces `dwell: —` instead of synthesizing a fake value (per M3).
- Photo URL normalization applied at insert time (legacy data fix from sky-log-insert.py).

### Backend abstraction (H2)

`backends/base.py` defines `Source` — an abstract class with `async setup()` / `async teardown()` and method-pair `entry_payload_to_normalized()` / `exit_payload_to_normalized()` (likewise for landing / takeoff). `backends/fr24.py` implements it by subscribing to FR24 events and translating each payload to the normalized `Sighting` / `Entry` / `Movement` dataclasses.

The internal coordinator never sees a raw FR24 payload — it consumes only normalized objects from `Source.emit_*()` callbacks. Adding a new backend means writing a new `Source` subclass and reusing the coordinator + storage unchanged.

### FR24 dependency (M4)

Strict requirement at runtime. `async_setup_entry` checks `hass.config_entries.async_entries("flightradar24")`; raises `ConfigEntryNotReady` if empty, with a user-actionable message. No soft-optional path; that's death-by-completeness for v0.1.

`manifest.json` sets `after_dependencies: ["flightradar24"]` so FR24 loads first when both are present — this is a load-ordering hint, not a hard requirement (HA can't enforce HACS deps).

### Large-attribute sensors (H1) — modified from reviewer recommendation

The reviewer counseled WebSocket commands over attribute-bearing sensors. We're keeping the attribute-bearing pattern because the existing dashboard YAML reads `state_attr(sensor.sky_log_recent, 'sightings')` everywhere — and we want a clean migration path. Hardening: every array-bearing sensor gets `entity_category=DIAGNOSTIC` (HA convention: not recorded by default in history dashboards) and the README ships a copy-paste `recorder.exclude` snippet.

For v0.2, a WebSocket command (`skywatch/sightings/recent`) will join the attribute path so the future custom card can avoid attribute churn.

### Jinja macros replacement (M6)

- `helo_codes()` → integration ships a default 84-code tuple in `const.py`; users can override via options. The classification (`is_helo`) becomes a precomputed boolean on each normalized `Sighting`.
- `is_regina_police_unit(f)` → becomes one watch-list entry of many. Watch list shape: `[{label, registration, aircraft_code, callsign_pattern, null_registration_required}]`. Each entry spawns its own `binary_sensor.skywatch_watch_<slug>` + the watch-list-match blueprint references it by entry slug.

### Regina-specific values (M6) — config-driven

| Value | Source |
|---|---|
| Home lat/lon | config flow `home_latitude` / `home_longitude` (defaults from `hass.config.latitude/longitude`) |
| Local airport IATA | config flow `airport_iata` |
| Radius (km) | config flow `radius_km` (default 50) |
| Overhead distance/altitude thresholds | config flow advanced options (defaults 5 km / 10,000 ft) |
| Timezone | config flow defaults to `hass.config.time_zone` |
| Helicopter ICAO codes | options flow; default = 84-code tuple |
| Military ICAO codes | options flow; default = ~50-code tuple |
| Watch list | options flow editor |

The legacy "Regina Police Air Unit" sensor becomes a configured watch entry: `{label: "Regina Police Air Unit", aircraft_code: "C182", callsign_pattern: "Blocked", null_registration_required: true}` — the user adds it themselves; the integration knows nothing about Regina.

### Testing strategy (per `02-test-strategy.md`)

- ruff lint + format only (no black, no mypy at v0.1)
- pytest with `pytest-homeassistant-custom-component`
- Coverage target: 80% line / 70% branch
- Schema migration tests with golden fixture (user copies live DB locally)
- No Playwright against live HA; disposable Docker container for E2E (deferred, user-driven)
- Manual checklist before user pushes anywhere

## Deviations from each subagent

| Source | Recommendation | Decision | Reason |
|---|---|---|---|
| Reviewer H1 | Don't ship attribute-bearing sensors | Keep them, mark DIAGNOSTIC | Existing dashboard YAML compat |
| Reviewer H2 | No backend abstraction in v0.1 | Ship adapter contract, only FR24 impl | User directive |
| Reviewer H3 | Two repos | One repo, no custom card v0.1 | User directive (one repo); reviewer's concern dodged by deferring true card |
| Reviewer L1 | Cut histogram/top-routes/military/police/GeoJSON | Keep all, parameterize Regina parts | User wants own setup feature-parity |
| Strategist §6 | Disposable HA container for E2E | Accepted; manual checklist only | No autonomous live-HA install |
| Inventory §1 | "Build into integration" for input_* | Document as user-created HA core entities | Integration platform for input_* isn't worth re-implementing |

## Open items (tracked as tasks)

- **Task #14:** HACS name collision check — runs at user-push time.
- **Golden fixture:** user copies live `/config/sky_sightings.db` into `tests/fixtures/golden_legacy.db` (gitignored). Required for the migration test.
- **GitHub handle + repo URL:** manifest currently references `TBD` placeholders. User edits before push.

## Implementation order (sequenced tasks)

1. Scaffold (done — repo init, manifest, hacs.json, README, LICENSE, planning docs preserved)
2. Storage layer + migrations + tests
3. Source adapter interface + FR24 backend
4. Coordinator
5. Sensor + binary_sensor platforms
6. Config flow
7. Legacy DB import service
8. Static path Leaflet map (parameterized)
9. Blueprints (3)
10. Example dashboard YAML template
11. Pytest test suite
12. hassfest + HACS validator runs
13. Manual verification checklist doc

Each becomes a separate commit with a focused diff. No squashing.
