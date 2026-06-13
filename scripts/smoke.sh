#!/usr/bin/env bash
# Smoke tests against a live HA with skywatch installed.
#
# Runs read-only HTTP GETs against the integration's entities and HTTP
# views. No state changes. Exits non-zero if anything fails.
#
# Env: HA_HOST (default 10.100.100.200), HA_TOKEN (required).
set -euo pipefail

HA_HOST="${HA_HOST:-10.100.100.200}"
HA_PORT="${HA_PORT:-8123}"
BASE="http://${HA_HOST}:${HA_PORT}"
HEADERS=(-H "Authorization: Bearer ${HA_TOKEN:?HA_TOKEN env var required}")

PASS=0
FAIL=0

check() {
  local label="$1"; shift
  if "$@" > /dev/null 2>&1; then
    echo "  ✓ ${label}"
    PASS=$((PASS+1))
  else
    echo "  ✗ ${label}"
    FAIL=$((FAIL+1))
  fi
}

check_state_exists() {
  local entity="$1"
  local resp
  resp=$(curl -sf "${HEADERS[@]}" "${BASE}/api/states/${entity}")
  echo "$resp" | python3 -c "import json,sys; d=json.load(sys.stdin); state=d.get('state'); exit(0 if state not in ('unavailable', None, 'unknown') else 1)"
}

check_attr() {
  local entity="$1"
  local key="$2"
  curl -sf "${HEADERS[@]}" "${BASE}/api/states/${entity}" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if '${key}' in (d.get('attributes') or {}) else 1)"
}

check_url() {
  local url="$1"
  local needle="${2:-}"
  local resp
  resp=$(curl -sf "${HEADERS[@]}" "${BASE}${url}")
  [[ -z "$needle" ]] && return 0
  echo "$resp" | grep -q "$needle"
}

echo "==> Entity existence + state"
for e in \
  sensor.sightings_today \
  sensor.sightings_this_week \
  sensor.sightings_all_time \
  sensor.recent_sightings \
  sensor.overhead_sightings \
  sensor.airport_movements_today \
  sensor.aircraft_in_area \
  binary_sensor.aircraft_present \
  binary_sensor.helicopter_overhead
do
  check "${e}" check_state_exists "$e"
done

echo "==> Attribute shape"
check "sensor.recent_sightings has 'page' attr" check_attr sensor.recent_sightings page
check "sensor.recent_sightings has 'total_pages' attr" check_attr sensor.recent_sightings total_pages
check "sensor.sightings_all_time has 'top_airlines' attr" check_attr sensor.sightings_all_time top_airlines

echo "==> HTTP views"
check_geojson_type() {
  curl -sf "${HEADERS[@]}" "${BASE}/api/skywatch/flights.geojson" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('type') == 'FeatureCollection' else 1)"
}
check "/api/skywatch/flights.geojson returns FeatureCollection" check_geojson_type
check "/api/skywatch/flights.geojson includes 'home' field" check_url "/api/skywatch/flights.geojson" '"home"'
check "/api/skywatch/flights.geojson includes 'radius_m' field" check_url "/api/skywatch/flights.geojson" '"radius_m"'
check "/api/skywatch/map serves Leaflet HTML" check_url "/api/skywatch/map" "leaflet"
check "/api/skywatch/map references the geojson endpoint" check_url "/api/skywatch/map" "/api/skywatch/flights.geojson"

echo
echo "==> ${PASS} passed, ${FAIL} failed"
[[ $FAIL -eq 0 ]]
