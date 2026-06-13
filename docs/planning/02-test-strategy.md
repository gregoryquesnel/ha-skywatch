# Test Strategy (Pre-Push Validation)

> Designed by a `Plan`-agent test-strategy review, 2026-06-13. Preserved as the gate before phase 6 sign-off.

## 1. Static / Lint

**Must-have (block release):**
- **hassfest** — catches manifest.json defects (bad domain, missing required keys, version mismatches, broken imports). See §8.
- **HACS action** — validates `hacs.json`, repo structure, README presence. See §9.
- **ruff** with `select = ["E","F","W","I","B","UP","SIM","PL","RUF"]`, line-length 100. Command: `ruff check custom_components/skywatch tests/`. Auto-fix with `ruff check --fix`.
- **ruff format** (replaces black entirely; one tool, faster, identical formatting).

**Skip:**
- **black** — redundant with `ruff format`.
- **mypy** — opinionated skip for a v0.1 HACS bundle. Revisit at v1.0.

## 2. Python Unit Tests (pytest)

**Coverage target: 80% line / 70% branch for `custom_components/skywatch/`.** Lower acceptable for `__init__.py` setup glue; higher (90%+) mandatory for storage and matcher.

**MUST have tests:**

- **`storage.py`** (highest priority — data loss is the worst possible defect): schema bootstrap on empty DB; ALTER-ladder idempotency; insert/select round-trip for `sightings`, `entries`, `airport_movements`; `normalize_photo_url` (the `https:https://` mangling); int/float coercion edge cases; the 2-hour TTL prune; the one-time `aircraft_photo` rewrite (idempotent).
- **`coordinator.py`**: `_async_update_data` returns expected shape; backend-error path sets `last_update_success=False`; deduplication of entry/exit events for same `flight_id`.
- **`backends/base.py` + `backends/fr24.py`**: abstract base contract; FR24 backend's event parsing. Mock `hass.bus.async_listen`.
- **`watch_matcher.py`**: registration-glob match; callsign match; flight number match; case-insensitivity; empty watch-list returns no match.
- **`categorize.py`**: aircraft_code lookup tables, fallback to civil, helo-by-model-string detection.

**Mock targets:**
- `hass`: use `pytest-homeassistant-custom-component`'s `hass` fixture.
- FR24 events: synthesize via `hass.bus.async_fire("flightradar24_exit", PAYLOAD)`. Build a fixture file `tests/fixtures/fr24_payloads.json`.
- SQLite: `tmp_path / "sky.db"` — never patch `Path("/config/...")`.

## 3. HA Integration Tests (pytest-homeassistant-custom-component)

`conftest.py` adds `enable_custom_integrations` autouse fixture.

**Must-have:**
- Config flow happy path: form submission → entry created → entities appear.
- Config flow invalid input: empty lat/lon, malformed watch-list, duplicate entry.
- Options flow: changing watch-list reloads coordinator without re-creating entry.
- Entity registration: assert exact entity IDs — this is the user-facing contract.
- Coordinator update on fired event: `hass.bus.async_fire("flightradar24_exit", payload)`; assert sensor state changed.
- Unload: succeeds; entities unregister cleanly.

## 4. Schema Migration Tests

For each migration step in the ladder, three tests:

1. **Forward-clean**: empty DB → run migration → assert final schema via `PRAGMA table_info`.
2. **Forward-from-prior**: programmatically construct a DB at version N-1, insert 3 rows, run migration, assert rows still readable, no row count change.
3. **Idempotent**: run migration twice; second run is no-op.

**Real existing DB test (golden fixture):**

The live DB lives at `/config/sky_sightings.db` on the HA host — not in this repo.
- Have the user run `scp ha:/config/sky_sightings.db tests/fixtures/golden_legacy.db` (manual, one-time, gitignored).
- `tests/test_migrations_golden.py` skips when fixture absent, otherwise: copies fixture to `tmp_path`, runs all migrations, asserts row counts unchanged, asserts no `https:https://` strings remain.

## 5. Card Tests (Vitest)

v0.1 ships no custom card — the Leaflet map serves via `register_static_path`. Defer Vitest until v0.2 when the card emerges.

## 6. Playwright E2E — do NOT install into live HA

**Recommended path: documented manual recipe, not autonomous install.**

Installing a v0.1 integration into the user's production HA before code review = highest-blast-radius action. Risks: entity-ID collisions, DB writes colliding with existing pipeline, recorder pollution.

**Instead, ship:**
- `tests/e2e/playwright-manual.md` — numbered recipe on disposable HA Docker container.
- `tests/e2e/verify-card.spec.ts` — Playwright script the recipe references.
- The `mise run verify:browser` task in ha-tinker is **not** what you want — it points at the user's live HA.

## 7. Manual Verification Checklist (user, before approving push)

Ordered by risk-of-undetected-bug:

1. Run all migration tests against the golden DB fixture.
2. Run `pytest --cov` locally, confirm thresholds.
3. Run hassfest + HACS action.
4. Spin disposable HA in Docker, install integration, complete config flow.
5. Manually fire synthetic `flightradar24_exit`; verify sighting row + sensor update.
6. Load card on dashboard; verify map renders + marker.
7. Run `ruff check && ruff format --check`.
8. Blueprint import test in disposable HA.
9. README rendering review on GitHub.

Steps 1-3 non-negotiable. 4-6 real-world smoke. 7-9 belt-and-suspenders.

## 8. Hassfest — Invocation

```bash
docker run --rm -v "$PWD":/github/workspace \
  ghcr.io/home-assistant/hassfest:latest
```

Inspects: `manifest.json` (domain matches dir, version PEP 440, `iot_class` set, `requirements` parse), `strings.json`/`translations/en.json` shape, `services.yaml` schema, `config_flow: true` consistency.

**Blocks release:** any non-zero exit.

## 9. HACS Validator — Invocation

```bash
docker run --rm -v "$PWD":/github/workspace \
  -e INPUT_CATEGORY=integration \
  -e GITHUB_REPOSITORY=owner/ha-skywatch \
  ghcr.io/hacs/action:main
```

Inspects: `hacs.json`, README presence, root has no stray files, integration dir naming matches manifest domain.

**Blocks release:** missing `hacs.json`, missing README, manifest/domain mismatch.
