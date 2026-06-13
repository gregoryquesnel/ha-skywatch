# Feature gap analysis — ha-tinker sky → ha-skywatch v0.1

> Produced 2026-06-13 after the v0.1 live-HA install verification. Compares the
> personal-install full-feature sky tab against the v0.1 HACS bundle and
> identifies what's missing, ranked by user-value × implementation effort.
> Preserved as the reference for v0.2 scope decisions.

## 1. Feature parity scorecard

| Category | Status | Notes |
|----------|--------|-------|
| Core sensors | ✅ Ported | 12 sensors + 2 binary + generalized per-watch |
| Queries | ✅ Ported | All 8 original + 2 new (hour_histogram, overhead) |
| Dashboard parity | ⚠️ Partial | ~75% coverage; photos, map polish, some visualizations missing |
| Map UX | ⚠️ Degraded | Simplified Leaflet; intentional v0.1 cut |
| Database | ✅ Improved | v0.1 has all the indexes the legacy DB lacked |
| Architecture | ✅ Better | Coordinator > command_line; config flow > hardcoding |
| Parameterization | ✅ Better | Regina values config-driven; no list duplication |
| Automation | ✅ Simplified | Blueprints + coordinator pattern replace bespoke automations |
| Testability | ✅ Better | 147 unit tests + smoke + Playwright |

## 2. Missing features by severity

### Critical (visible regressions from tinker)
1. **Map silhouettes + altitude coloring** — tinker has 5 SVG aircraft icons + 5-tier altitude color ramp + heading-based CSS rotation. Skywatch v0.1 is plain colored dots. Biggest visual loss. Effort: substantial (4-6 h). Reuse: high.
2. **Trail rendering on map** — `flight_positions` table is populated with 30-min sliding window, but the simplified map doesn't draw the polylines. Data is ready, presentation isn't. Effort: moderate (2-3 h). Reuse: high.
3. **Photo column + JetPhotos full-size URL transformation** — `aircraft_photo` is already in DB and recent_sightings attribute, but the example dashboard doesn't render it. Tinker's regex `https:https://` strip + `/200/ → /full/` + `_tb.jpg → .jpg` swap is straightforward to port. Effort: moderate (1-2 h). Reuse: medium (FR24-specific photos).

### High (dashboard polish; data exists, just isn't rendered)
4. **Hour-of-day histogram bar chart** — sensor `skywatch_sightings_hour_of_day` exposes `buckets[24]` and `max_n`, but example dashboard doesn't render the bar chart. Trivial Jinja markdown copy from tinker. Effort: trivial (30 min). Reuse: high.
5. **Top routes bar chart** — same situation: sensor data is there, dashboard doesn't show the bar chart. Effort: trivial (30 min). Reuse: high.
6. **Rare aircraft list** — `skywatch_sightings_all_time` has `rare_aircraft` attribute (one-off models), not rendered in example dashboard. Effort: trivial (30 min). Reuse: high.
7. **FlightAware + Wikipedia links in sightings table** — `aircraft_info_url` is already a row attribute, the URL just isn't wired into the markdown anchors. Effort: trivial (15 min). Reuse: high.

### Medium (small feature adds)
8. **1h / 24h activity sensors (Sky Pulse)** — tinker has 3 tiles (1h / 24h / 7d); skywatch only has today / this_week / all_time. Add `query_active_1h()` + `query_active_24h()` to queries.py + 2 sensors. Effort: moderate (1-2 h). Reuse: high.
9. **Trending Worldwide section** — FR24's `sensor.flightradar24_most_tracked` is already in the user's install; tinker renders top-8 most-watched with emergency-squawk highlight. Skywatch could ship the YAML snippet in the example dashboard. Effort: trivial (30 min). Reuse: low (FR24-only).
10. **YQR delay tiles** — tinker shows `arrivals_delayed` / `departures_delayed` from FR24. Same as above: example dashboard YAML, no integration work. Effort: trivial (15 min). Reuse: low.

### Low (install-specific or minor polish)
11. **Audible range circle (8 km)** — nice visual aid on the map. Effort: moderate (1-2 h). Reuse: medium.
12. **Icon rotation by heading** — compass-aware marker orientation. Effort: moderate (1-2 h). Reuse: high.
13. **Watch entry `days_dark` warning** — when last_seen is >3 days ago, render a "silent for N days" markdown card. Useful for the police-air-unit pattern. Effort: moderate (1-2 h). Reuse: medium.
14. **Search clear button** — tiny UX. Effort: trivial (10 min). Reuse: high.

### Out-of-scope for skywatch
- C-GRPF-specific markdown card and offline warning — generalize as watch entry; user customizes
- YQR airport tiles + counters — example dashboard YAML, not integration responsibility
- FR24 controls (Add flight / Remove flight / API toggle) — owned by the FR24 integration, not skywatch
- Force-refresh automations (page / search) — coordinator already handles auto-refresh
- Jinja macros — replaced by config flow + classification module

## 3. Architectural carries explicitly rejected
- **shell_command + command_line sensors** — replaced by coordinator + executor pool. Async-safe, testable.
- **GeoJSON file I/O to `/config/www/sky-flights.json`** — replaced by `/api/skywatch/flights.geojson` HTTP endpoint. No write races, no filesystem permission concerns.
- **Hardcoded Regina values in JS + Jinja + Python** — replaced by config flow single source of truth.
- **Template sensor `sky_log_this_week` extracting attribute** — replaced by first-class coordinator sensor.

## 4. Recommended v0.2 scope

If shipping v0.2 in one focused session, the right cut is **Tier 1**:

**Tier 1 — quick wins, all dashboard YAML, ~2 hours total**
- 4 (hour histogram bar chart)
- 5 (top routes bar chart)
- 6 (rare aircraft list)
- 7 (FlightAware + Wikipedia links)
- 9 (Trending Worldwide example)
- 10 (YQR delay tile example)

These reuse data that's already in sensor attributes. Pure YAML. Zero integration code. Highest leverage per minute.

**Tier 2 — moderate effort, adds new sensors / data, ~half a session**
- 3 (photo column restoration)
- 8 (1h / 24h activity sensors)

**Tier 3 — substantial map work, full session**
- 1 (silhouettes + altitude coloring)
- 2 (trail rendering)
- 11 (audible range circle)
- 12 (icon rotation)

Saving the map overhaul (Tier 3) for a dedicated release means it gets the attention it deserves and doesn't drag down v0.2's "quick polish" character.
