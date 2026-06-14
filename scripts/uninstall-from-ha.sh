#!/usr/bin/env bash
# Uninstall ha-skywatch from a live Home Assistant.
#
# Removes /config/custom_components/skywatch and /config/www/skywatch-map.html.
# Does NOT remove /config/skywatch/sightings.db — your sightings history
# is preserved. Delete it manually if you want a clean teardown.
#
# Also does NOT remove the config_entry or registered entities — do that
# in the UI (Settings → Devices & Services → Skywatch → delete) BEFORE
# running this script, otherwise HA will complain about missing modules
# at next startup.
set -euo pipefail

HA_HOST="${HA_HOST:-10.100.100.200}"
HA_SSH_USER="${HA_SSH_USER:-hassio}"
HA_SSH_PORT="${HA_SSH_PORT:-22}"
RESTART=true

while (("$#")); do
  case "$1" in
    --no-restart) RESTART=false; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

SSH="ssh -p ${HA_SSH_PORT} -o StrictHostKeyChecking=no ${HA_SSH_USER}@${HA_HOST}"

echo "==> Target: ${HA_SSH_USER}@${HA_HOST}:${HA_SSH_PORT}"

cat <<EOF

WARNING: Have you removed the Skywatch config entry via the UI?
   Settings → Devices & Services → Skywatch → ⋮ → Delete

If not, HA may fail to start cleanly after this script runs (it'll
look for the missing module on every restart until the entry is
removed).

Press Ctrl+C now to abort, or Enter to continue.
EOF
read -r

echo "==> Removing /config/custom_components/skywatch (incl. bundled www/)"
$SSH "sudo rm -rf /config/custom_components/skywatch"

echo "==> /config/skywatch/sightings.db (sighting history) is preserved."
echo "    Remove manually with:  $SSH 'sudo rm -rf /config/skywatch'"

if $RESTART; then
  echo "==> Restarting HA"
  if [[ -n "${HA_TOKEN:-}" ]]; then
    curl -sf -X POST \
      -H "Authorization: Bearer ${HA_TOKEN}" \
      "http://${HA_HOST}:8123/api/services/homeassistant/restart" > /dev/null
    echo "==> Restart request sent."
  else
    echo "WARNING: HA_TOKEN not set — restart HA manually." >&2
  fi
fi
