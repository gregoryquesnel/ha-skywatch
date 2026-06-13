# Code Inventory — Sky Tab → Skywatch

> Produced by an `Explore` agent's read-through of the live ha-tinker sky subsystem, 2026-06-13. Preserved as the porting spec.

## 1. Entity Inventory

| Current entity_id | Current source | State | Key attributes | Planned skywatch entity | Notes |
|---|---|---|---|---|---|
| `sensor.sky_log_recent` | command_line | int (count) | `sightings` (array, ≤10), `page`, `total_pages`, `page_size`, `total_count` | `sensor.skywatch_log_recent` | Paginated; decorated with `exit_time_local`, `dwell_seconds`, `aircraft_info_url` |
| `sensor.sky_log_today` | command_line | int (count) | none | `sensor.skywatch_log_today` | Since local midnight; no array attr (busy-day risk) |
| `sensor.sky_log_search` | command_line | int (count) | `sightings` (array), `term` | `sensor.skywatch_log_search` | Search for `input_text.sky_log_search_term` substring |
| `sensor.sky_log_stats` | command_line | int (total) | `today`, `this_week`, `top_airlines`, `top_aircraft`, `rare_aircraft` | `sensor.skywatch_log_stats` | Lifetime aggregates + top-10s + rare one-offs |
| `sensor.sky_log_top_routes` | command_line | int (distinct routes) | `routes` (array of `{origin_iata, destination_iata, n}`) | `sensor.skywatch_log_top_routes` | Excludes null endpoints |
| `sensor.sky_log_overhead` | command_line | int (lifetime) | `recent_overhead` (array, ≤50) | `sensor.skywatch_log_overhead` | Subset: closest_km<5 AND altitude_ft<10,000 |
| `sensor.sky_log_hour_histogram` | command_line | int (total) | `buckets` (24-row), `max_n` | `sensor.skywatch_log_hour_histogram` | Hour-of-day distribution |
| `sensor.sky_military_sightings` | command_line | int (military) | `sightings` (array, ≤50) | `sensor.skywatch_military_sightings` | aircraft_code IN MILITARY_CODES |
| `sensor.sky_movements_today` | command_line | int | `movements` (array), `landed`, `took_off` | `sensor.skywatch_movements_today` | YQR arrivals + departures since midnight |
| `sensor.sky_watch_c_grpf` | command_line | int (sightings) | `last_seen`, `last_seen_local`, `last_seen_relative`, `last_callsign`, `last_flight_number`, `last_origin`, `last_destination`, `last_altitude_ft`, `last_closest_km`, `last_aircraft_model`, `recent` | `sensor.skywatch_watch_cgrpf` | Registration C-GRPF OR (C182 + Blocked + null reg) |
| `sensor.sky_flights_geojson` | command_line | int (aircraft count) | none (writes file) | `sensor.skywatch_flights_geojson` | Emits GeoJSON; 30-min trail retention |
| `sensor.sky_log_this_week` | template | int | none | `sensor.skywatch_log_this_week` | Extracts attribute from sky_log_stats |
| `binary_sensor.sky_has_aircraft` | template | bool | none | `binary_sensor.skywatch_has_aircraft` | flightradar24_current_in_area>0 |
| `binary_sensor.sky_helicopter_overhead` | template | bool | `helicopters` (array of callsigns) | `binary_sensor.skywatch_helicopter_overhead` | True if any aircraft_code IN helo_codes() |
| `input_number.sky_log_page` | input | float (1–20) | none | `input_number.skywatch_log_page` | Pagination control |
| `input_text.sky_log_search_term` | input | string | none | `input_text.skywatch_log_search_term` | Search substring |
| `input_boolean.sky_alerts_enabled` | input | bool | none | `input_boolean.skywatch_alerts_enabled` | Master alert toggle |
| `input_boolean.police_air_alerts_enabled` | input | bool | none | `input_boolean.skywatch_police_air_alerts_enabled` | Dedicated C-GRPF toggle |
| `input_datetime.sky_alerts_waking_start` | input | time | none | `input_datetime.skywatch_alerts_waking_start` | Quiet hours start |
| `input_datetime.sky_alerts_waking_end` | input | time | none | `input_datetime.skywatch_alerts_waking_end` | Quiet hours end |

## 2. Event Sources

### FR24 Integration Events

| Event type | Fired on | Payload fields (key ones) | Handler | Action |
|---|---|---|---|---|
| `flightradar24_entry` | Aircraft enters 50 km box | id, callsign, flight_number, aircraft_code, aircraft_model, aircraft_registration, airline, airline_iata, airport_origin_code_iata, airport_origin_city, airport_destination_code_iata, airport_destination_city, altitude, ground_speed, heading, vertical_speed, closest_distance, aircraft_photo_small, tracked_by_device | 1779100000002 (entry logger) | INSERT into `entries`; timestamp UTC |
| `flightradar24_entry` | (same) | (same) | 1779100000003 (helo alert) | Notify if helo + alerts enabled + time-window ok |
| `flightradar24_entry` | (same) | (same) | 1779200000001 (police air alert) | Notify if matches C-GRPF fingerprint + police_air_alerts_enabled |
| `flightradar24_exit` | Aircraft leaves box | (same + exit context) | 1779100000001 (sighter) | INSERT into `sightings`; join entry_time; compute dwell |
| `flightradar24_area_landed` | Aircraft landed | (same + airport) | 1779100000004 | INSERT into `airport_movements` (landed) |
| `flightradar24_area_took_off` | Aircraft took off | (same + airport) | 1779100000005 | INSERT into `airport_movements` (took_off) |

### Automation State Change Triggers

| Trigger entity | Condition | Handler | Action |
|---|---|---|---|
| `input_number.sky_log_page` | State changes | 1779300000001 | Force-refresh `sensor.sky_log_recent` |
| `input_text.sky_log_search_term` | State changes | 1779300000002 | Force-refresh `sensor.sky_log_search` |

## 3. SQLite Schema (CURRENT)

### Table: `sightings`

```sql
CREATE TABLE IF NOT EXISTS sightings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exit_time TEXT NOT NULL,
  flight_number TEXT,
  callsign TEXT,
  airline TEXT,
  airline_iata TEXT,
  aircraft_code TEXT,
  aircraft_model TEXT,
  registration TEXT,
  origin_iata TEXT,
  origin_city TEXT,
  destination_iata TEXT,
  destination_city TEXT,
  altitude_ft INTEGER,
  ground_speed_kt INTEGER,
  closest_km REAL,
  aircraft_photo TEXT,
  tracked_by_device TEXT,
  entry_time TEXT,         -- added by ALTER
  heading INTEGER,         -- added by ALTER
  vertical_speed INTEGER   -- added by ALTER
);
CREATE INDEX IF NOT EXISTS idx_exit_time ON sightings(exit_time DESC);
CREATE INDEX IF NOT EXISTS idx_callsign ON sightings(callsign);
CREATE INDEX IF NOT EXISTS idx_airline_iata ON sightings(airline_iata);
```

**Schema issues (fix in skywatch v1):**
- Missing index on `aircraft_code` (military/helo filtering O(N))
- Missing index on `altitude_ft`, `closest_km` (overhead filtering O(N))
- Missing index on `origin_iata`, `destination_iata` (route aggregation O(N))
- No `on_ground` boolean (would speed overhead filtering)

### Table: `entries`

```sql
CREATE TABLE IF NOT EXISTS entries (
  flight_id TEXT PRIMARY KEY,
  entry_time TEXT NOT NULL,
  callsign TEXT,
  flight_number TEXT,
  aircraft_code TEXT,
  aircraft_model TEXT
);
CREATE INDEX IF NOT EXISTS idx_entries_entry_time ON entries(entry_time);
```

**Issue:** TTL pruned only on script run; if script stops, rows persist.

### Table: `airport_movements`

```sql
CREATE TABLE IF NOT EXISTS airport_movements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_time TEXT NOT NULL,
  direction TEXT NOT NULL,   -- 'landed' or 'took_off'
  airport_iata TEXT,
  flight_number TEXT,
  callsign TEXT,
  airline TEXT,
  airline_iata TEXT,
  aircraft_code TEXT,
  aircraft_model TEXT,
  registration TEXT,
  origin_iata TEXT,
  destination_iata TEXT,
  aircraft_photo TEXT
);
CREATE INDEX IF NOT EXISTS idx_movement_time ON airport_movements(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_movement_airport ON airport_movements(airport_iata);
CREATE INDEX IF NOT EXISTS idx_movement_direction ON airport_movements(direction);
```

### Table: `flight_positions` (trail retention, 30-min)

```sql
CREATE TABLE IF NOT EXISTS flight_positions (
  flight_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  PRIMARY KEY (flight_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_flight_positions_ts ON flight_positions(ts);
CREATE INDEX IF NOT EXISTS idx_flight_positions_flight ON flight_positions(flight_id);
```

## 4. Regina-Specific Values

### Geography & Airport
- Home: lat 50.4798, lon -104.7072
- YQR: lat 50.4319, lon -104.6657
- Radius: 50 km
- Audible: 8 km
- Overhead: closest_km<5 AND altitude_ft<10,000
- Locations: `sky-map.html` lines 160–427, `sky-log-query.py` line 43

### Timezone
- `America/Regina` (UTC−6, no DST)

### Regina Police Air Unit (C-GRPF)
- Registration: C-GRPF
- Aircraft: C182 (Cessna 182T Skylane)
- Fingerprint: `aircraft_code='C182' AND callsign='Blocked' AND registration IS NULL`
- Locations: `ha_macros.jinja` 175–185, dashboard-sky 251–283, configuration.yaml 2215

### Military ICAO Codes
`/config/scripts/sky-log-query.py` lines 408–418. (Inventory listed verbatim.)

### Helicopter ICAO Codes (84)
`sky-map.html` 174–183 is source of truth; mirrored in `ha_macros.jinja` 159–172 and `sky-flights-geojson.py` 65–77.

## 5. External Dependencies

### HACS Integrations
- **Flightradar24** (`AlexandrErohin/home-assistant-flightradar24`):
  - Events: `flightradar24_entry`, `_exit`, `_area_landed`, `_area_took_off`
  - Sensors: `flightradar24_current_in_area`, `_airport_arrivals`, `_airport_departures`, `_airport_arrivals_delayed`, `_airport_departures_delayed`, `_most_tracked`
  - Configuration: API key required; 15 s scan_interval

### HACS Cards
- **flightradar-flight-card** — used in dashboard-sky.yaml 60–78 for live tables

### HA Core Features Used
- template, command_line, recorder (with excludes), automation, input_*

## 6. Macros & Template Logic

### `helo_codes()` — `/config/custom_templates/ha_macros.jinja` 158–173
Returns JSON array of 84 ICAO codes. Callers: dashboard markdown, `binary_sensor.sky_helicopter_overhead`, automation 1779100000003. Replace with integration-side computed binary_sensor or lookup table.

### `is_regina_police_unit(f)` — `/config/custom_templates/ha_macros.jinja` 175–185
Returns "True"/"False" if flight matches C-GRPF privacy-block triple. Replace with a watch-list entry in the integration (label="Regina Police", match by aircraft_code + callsign + null reg).

## 7. Recorder/Exclude Implications

| Entity | Attribute | Typical | Excluded? |
|---|---|---|---|
| `sky_log_recent` | `sightings` (10 rows) | ~8 KB | yes |
| `sky_log_overhead` | `recent_overhead` (50 rows) | ~12 KB | yes |
| `sky_military_sightings` | `sightings` (50 rows) | ~35 KB worst | yes |
| `sky_movements_today` | `movements` (30 rows) | ~6 KB | yes |
| `sky_log_stats` | top_airlines/aircraft/rare | ~2 KB | no |

Skywatch default: `entity_category=DIAGNOSTIC` on the array-bearing sensors + documented `recorder.exclude` snippet in README.

## 8. Migration Concerns

- **Old DB:** `/config/sky_sightings.db`
- **New DB:** `/config/skywatch/sightings.db`
- **Tool:** `skywatch.import_legacy_db` service (manual, fail-loud)
- **Entity ID prefix change:** `sky_*` → `skywatch_*`
- **User-facing migration guide:** required in README

## 9. Source Backend Abstraction

### FR24 payload (key fields)
```json
{
  "id": "flight_id_hex",
  "callsign": "AAL123" | "Blocked" | null,
  "flight_number": "AA123" | null,
  "aircraft_code": "B738",
  "aircraft_model": "Boeing 737-8 MAX",
  "aircraft_registration": "N123AB" | null,
  "airline": "American Airlines",
  "airline_iata": "AA",
  "airport_origin_code_iata": "YYC",
  "airport_origin_city": "Calgary",
  "airport_destination_code_iata": "YVR",
  "airport_destination_city": "Vancouver",
  "altitude": 10500,
  "ground_speed": 450,
  "heading": 270,
  "vertical_speed": 1200,
  "closest_distance": 3.5,
  "latitude": 50.5,
  "longitude": -104.6,
  "aircraft_photo_small": "https://cdn.jetphotos.com/...",
  "tracked_by_device": "dev_123abc"
}
```

### Skywatch adapter interface
- `async register_flight_entry(payload) → Entry`
- `async register_flight_exit(payload) → Sighting`
- `async register_landing(payload, airport) → Movement`
- `async register_takeoff(payload, airport) → Movement`

Normalized internal model `Sighting` carries the union of fields above plus computed `entry_time`, `dwell_seconds`, `is_helo`, `is_military`, `is_overhead`.
