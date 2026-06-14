#!/usr/bin/env bash
# Install ha-skywatch into a live Home Assistant for manual testing.
#
# Copies custom_components/skywatch/ to <HA>:/config/custom_components/
# and www/skywatch-map.html to <HA>:/config/www/, then restarts HA via
# the REST API. Does NOT touch your existing ha-tinker sky_* setup —
# both run in parallel, writing to different DBs and exposing different
# entity prefixes.
#
# Prereqs:
#   - SSH access to HA (defaults: 10.100.100.200, user hassio, port 22)
#   - HA_TOKEN env var set (Long-Lived Access Token)
#
# Usage:
#   scripts/install-to-ha.sh                # install + restart HA
#   scripts/install-to-ha.sh --no-restart   # install but don't restart
#   scripts/install-to-ha.sh --dry-run      # show what would be copied
#
# Overrides via env: HA_HOST, HA_SSH_USER, HA_SSH_PORT.
set -euo pipefail

HA_HOST="${HA_HOST:-10.100.100.200}"
HA_SSH_USER="${HA_SSH_USER:-hassio}"
HA_SSH_PORT="${HA_SSH_PORT:-22}"
RESTART=true
DRY_RUN=false

while (("$#")); do
  case "$1" in
    --no-restart) RESTART=false; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) sed -n '1,/^set -euo/p' "$0" | grep -E "^# "; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH="ssh -p ${HA_SSH_PORT} -o StrictHostKeyChecking=no ${HA_SSH_USER}@${HA_HOST}"

echo "==> Target: ${HA_SSH_USER}@${HA_HOST}:${HA_SSH_PORT}"
echo "==> Source: ${REPO_ROOT}"

if $DRY_RUN; then
  echo "(dry run — would copy)"
  rsync -nav --delete -e "ssh -p ${HA_SSH_PORT}" \
    --exclude='__pycache__' --exclude='*.pyc' \
    "${REPO_ROOT}/custom_components/skywatch/" \
    "${HA_SSH_USER}@${HA_HOST}:/config/custom_components/skywatch/" || true
  echo "(dry run — would copy www/skywatch-map.html → /config/www/)"
  exit 0
fi

echo "==> Ensuring /config/custom_components exists"
$SSH "sudo mkdir -p /config/custom_components && sudo chown -R ${HA_SSH_USER}:${HA_SSH_USER} /config/custom_components"

echo "==> Syncing custom_components/skywatch/ (includes www/skywatch-map.html)"
rsync -av --delete \
  -e "ssh -p ${HA_SSH_PORT}" \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  "${REPO_ROOT}/custom_components/skywatch/" \
  "${HA_SSH_USER}@${HA_HOST}:/config/custom_components/skywatch/"

if $RESTART; then
  echo "==> Restarting HA"
  if [[ -z "${HA_TOKEN:-}" ]]; then
    echo "WARNING: HA_TOKEN not set — skipping API restart. Restart HA manually." >&2
  else
    curl -sf -X POST \
      -H "Authorization: Bearer ${HA_TOKEN}" \
      -H "Content-Type: application/json" \
      "http://${HA_HOST}:8123/api/services/homeassistant/restart" \
      > /dev/null
    echo "==> Restart request sent. HA will be unavailable for ~30 s."
  fi
fi

cat <<EOF

==> Install complete.

Next steps (in HA UI):
  1. Settings → Devices & Services → Add Integration → "Skywatch"
  2. Walk the config flow (lat/lon prefilled, IATA optional, radius 50 km).
  3. Verify entities appear under Settings → Devices & Services → Skywatch.
  4. (Optional) Service skywatch.import_legacy_db to bring your existing
     /config/sky_sightings.db rows into the new /config/skywatch/sightings.db.
  5. Deploy the test dashboard:  mise run deploy:test-dashboard
  6. Run Playwright smoke:        mise run verify:browser
EOF
