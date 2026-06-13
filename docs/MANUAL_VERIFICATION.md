# Manual verification checklist

This is the gate to run **before** pushing `ha-skywatch` to an external
GitHub repo or submitting to the HACS default list. Items are ordered
by risk-of-undetected-bug — the data-loss / install-broken checks come
first, the cosmetic ones last.

Run every step. Where a step fails, fix and re-run from that point;
don't skip ahead.

---

## 1. Static + unit-test gate (5 min, no live HA)

```bash
mise install                 # installs Python 3.12
mise run setup               # pytest + ruff into .venv
mise run test                # pytest tests/unit -v
mise run lint                # ruff check + format --check
mise run cov                 # pytest --cov; coverage 80%+ line, 70%+ branch
```

Every line-item must be green. Coverage shortfall is acceptable on the
HA-dependent modules (coordinator, __init__, sensor, binary_sensor,
config_flow, services) — step 4 below covers them with the real
hassfest + a disposable HA container.

## 2. Golden-DB migration test (10 min, requires live HA SSH access)

The riskiest scenario: someone with a real legacy `sky_sightings.db`
runs the `skywatch.import_legacy_db` service. If the import corrupts
or loses rows, it's unrecoverable without a backup.

```bash
# Copy your live legacy DB into the test fixture path (gitignored).
scp homeassistant.local:/config/sky_sightings.db tests/fixtures/golden_legacy.db

# Optional: add a per-fixture migration test if you haven't yet. The
# test below is recommended but not auto-run because the fixture is
# absent in fresh checkouts.
cat > tests/unit/test_migrations_golden.py <<'PY'
"""Migration against a real legacy DB — skipped when fixture absent."""
from pathlib import Path
import shutil
import sqlite3
import pytest
from custom_components.skywatch.legacy_import import import_legacy_db
from custom_components.skywatch.storage import open_db

FIXTURE = Path(__file__).parent.parent / "fixtures" / "golden_legacy.db"

@pytest.mark.skipif(not FIXTURE.exists(), reason="golden fixture absent")
def test_golden_migration_preserves_row_counts(tmp_path: Path) -> None:
    legacy_copy = tmp_path / "legacy.db"
    shutil.copy(FIXTURE, legacy_copy)

    target = tmp_path / "skywatch.db"
    target_conn = open_db(target)
    try:
        summary = import_legacy_db(target_conn, legacy_copy)
    finally:
        target_conn.close()

    legacy_conn = sqlite3.connect(FIXTURE)
    legacy_sightings = legacy_conn.execute("SELECT COUNT(*) FROM sightings").fetchone()[0]
    legacy_entries = legacy_conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    legacy_movements = legacy_conn.execute("SELECT COUNT(*) FROM airport_movements").fetchone()[0]
    legacy_conn.close()

    assert summary["sightings_inserted"] == legacy_sightings
    assert summary["entries_inserted"] == legacy_entries
    assert summary["movements_inserted"] == legacy_movements
PY

mise run test
```

If row counts mismatch, **stop** and root-cause before going further.

## 3. hassfest + HACS validator (5 min, requires Docker)

Both validators run as containers and need no live HA.

```bash
docker run --rm \
  -v "$PWD":/github/workspace \
  ghcr.io/home-assistant/hassfest:latest
# Expected: exit 0. Fails on bad manifest.json, missing strings.json key,
# requirements not pinned, etc.

docker run --rm \
  -v "$PWD":/github/workspace \
  -e INPUT_CATEGORY=integration \
  -e GITHUB_REPOSITORY=<your-handle>/ha-skywatch \
  ghcr.io/hacs/action:main
# Expected: exit 0. Fails on missing hacs.json, missing README, etc.
```

Both should exit 0. Persistent failures are blockers.

## 4. Disposable HA Docker — full install + config flow (15 min)

The first time skywatch loads inside a real HA, lots can go wrong
(import paths, ConfigEntryNotReady cycle, entity-registry collisions,
DB path permissions). Test in a throwaway container, **never** in your
production HA.

```bash
mkdir -p /tmp/skywatch-test-config
docker run --rm \
  --name ha-test \
  -p 8124:8123 \
  -v /tmp/skywatch-test-config:/config \
  -v "$PWD/custom_components/skywatch":/config/custom_components/skywatch \
  ghcr.io/home-assistant/home-assistant:stable
# wait ~30s for HA to boot, then open http://localhost:8124
```

Inside the test HA:

  1. **Onboard** (create user, set location).
  2. **Install Flightradar24** integration via HACS (the throwaway HA needs
     HACS too — easier: `pip install pyflightdata` if just testing
     event handling, or skip FR24 and verify ConfigEntryNotReady fires).
  3. **Add Skywatch** via Settings → Devices & Services → Add → "Skywatch".
  4. Walk the config flow. Form should pre-fill lat/lon from HA config;
     IATA empty is OK; radius 50 km default; click Submit.
  5. Verify `sensor.skywatch_log_today`, `binary_sensor.skywatch_has_aircraft`
     etc. appear under Settings → Devices & Services → Skywatch → Entities.
  6. Open Settings → Devices & Services → Skywatch → Configure → walk the
     options flow. Add a watch entry like
     `{"slug":"test","label":"Test","registration":"C-TEST"}` and save.
     The integration reloads. A new `sensor.skywatch_watch_test` appears.
  7. Open Developer Tools → Events → fire a synthetic exit event:
     ```
     event_type: flightradar24_exit
     event_data:
       id: synthetic_test
       callsign: TEST123
       aircraft_code: B738
       aircraft_model: Test 737
       closest_distance: 4.0
       altitude: 8500
     ```
     Then refresh the entities page. `sensor.skywatch_log_today` increments,
     and a row appears in `state_attr(sensor.skywatch_log_recent, 'sightings')`.
  8. (Optional) Service-call `skywatch.import_legacy_db` with a path
     to a small legacy DB (copy `tests/fixtures/golden_legacy.db` into
     the container's /config/ first).
  9. Tear down: `docker stop ha-test`, `rm -rf /tmp/skywatch-test-config`.

## 5. Recorder-load check (5 min)

The array-bearing sensors emit ~10 KB attributes. Without a
`recorder.exclude` snippet, the user's history DB swells.

Verify the README ships the snippet below and that it pastes cleanly:

```yaml
# Recommended addition to your configuration.yaml.
recorder:
  exclude:
    entities:
      - sensor.skywatch_log_recent
      - sensor.skywatch_log_search
      - sensor.skywatch_log_overhead
      - sensor.skywatch_military_sightings
      - sensor.skywatch_movements_today
      - sensor.skywatch_log_hour_histogram
```

## 6. Blueprint import smoke (5 min, in disposable HA from step 4)

Settings → Automations & Scenes → Blueprints → Import → paste the raw
GitHub URL for each of the three blueprints (after-push step; for the
local-only verification, copy/paste from `blueprints/automation/skywatch/`).

For each, hit "Save automation" with the defaults and verify HA
doesn't reject the YAML.

## 7. HACS name-collision check (5 min, browser)

Open both of these and search for "skywatch":

  - <https://github.com/hacs/default/blob/main/integration>
  - <https://github.com/hacs/default/blob/main/plugin>

If "skywatch" or a near-collision (e.g., `ha-skywatch`, `aerowatch`,
`adsbwatch`) appears, rename your bundle before push. Recommended
fallback: `aerolog`, `skyview-ha`, `radarwatch`. Update:

  - `custom_components/skywatch/manifest.json` `domain`
  - `custom_components/skywatch/const.py` `DOMAIN`
  - All entity-id prefixes (`skywatch_*`) in `sensor.py` + `binary_sensor.py`
  - Repo dir name `ha-skywatch`
  - `hacs.json` `name`
  - Blueprint `source_url`s
  - Dashboard template entity references

Renaming is mechanical but high-touch — better to discover the
collision now than after first user-install.

## 8. Pre-push manifest substitutions (2 min)

Search the repo for `TBD` and replace with your real GitHub handle/repo
URL:

```bash
grep -rn TBD custom_components/ blueprints/ README.md hacs.json
# Update each match.
```

Specifically:

  - `manifest.json` → `documentation`, `issue_tracker`, `codeowners`
  - `blueprints/automation/skywatch/*.yaml` → `source_url`
  - `README.md` → install instructions, HACS button

## 9. README rendering check (5 min)

Push to a **draft branch on a sandbox repo** (not the real `ha-skywatch`
repo yet) and verify the README renders correctly on GitHub:

  - Headings render
  - Code blocks have syntax highlighting
  - Internal links work
  - Status badges (if any) load

Delete the sandbox branch before continuing.

## 10. Final push

Only after every step above is green:

```bash
git remote add origin git@github.com:<your-handle>/ha-skywatch.git
git push -u origin main
git tag -a v0.1.0 -m "First release"
git push origin v0.1.0
```

Don't submit to HACS default repo until you've used the integration
yourself in your live HA for at least a week. The HACS PR is one-way
(removing a default-repo entry is messy).

---

## Failure responses

| Failure | Likely cause | Fix |
|---|---|---|
| pytest: `sqlite3.OperationalError: database legacy is locked` | Forgot to commit before DETACH in legacy_import.py | Re-apply commit-before-DETACH pattern |
| hassfest: `manifest.json: invalid version` | manifest `version` not PEP 440 | Use `0.1.0` not `0.1` |
| HACS action: `category mismatch` | hacs.json missing `name` | Add `"name": "Skywatch"` |
| HA load: `ConfigEntryNotReady: FR24 not loaded` | FR24 integration absent | Install AlexandrErohin/home-assistant-flightradar24 first |
| HA load: `error setting up integration` | Coordinator's DB dir missing | `__init__.py` should `mkdir(parents=True, exist_ok=True)` — verify |
| Sensor never updates | Coordinator not registered or refresh exception | Check HA logs; coordinator uses `update_interval=30s` |
