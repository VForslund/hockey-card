#!/usr/bin/env bash
# The quarantine test bench ("night-sim"): a disposable Home Assistant
# container running the real image, with ONLY this integration installed,
# polling the director (the scripted fake API).
#
# BOTH containers live on an isolated docker network — nothing is exposed
# on the host at any point (production HA never involved: separate scratch
# config, no published ports, no devices, fake API key).
#
# Usage: ./scripts/nightsim.sh [scenario-name]     (default: full_game)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER="${CONTAINER:-hockey-nightsim}"
DIRECTOR_CONTAINER="hockey-director"
NETWORK="hockey-sim"
SCENARIO="${1:-full_game}"
NS=/tmp/opencode/nightsim
IMAGE=ghcr.io/home-assistant/home-assistant:stable

cleanup() {
  docker rm -f "$CONTAINER" "$DIRECTOR_CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "$NETWORK" >/dev/null 2>&1 || true

# --- clean slate ----------------------------------------------------------
# Scratch files are root-owned (written by containers); purging from the
# host fails with permission denied, so purge via a throwaway container.
docker rm -f "$CONTAINER" "$DIRECTOR_CONTAINER" >/dev/null 2>&1 || true
if [ -d "$NS" ]; then
  docker run --rm -v "$NS":/ns --entrypoint sh "$IMAGE" \
    -c 'rm -rf /ns' >/dev/null 2>&1 || rm -rf "$NS" || true
fi
mkdir -p "$NS/config/.storage" "$NS/config/custom_components"

# --- scratch config: just enough HA to boot, plus debug logs -------------
cat > "$NS/config/configuration.yaml" <<'YAML'
default_config:
logger:
  default: info
  logs:
    custom_components.hockey_score: debug
YAML

# Seed the config entry so the integration loads at boot without the UI
# flow (the config flow itself gets human-verified in the Phase 2 dogfood).
cat > "$NS/config/.storage/core.config_entries" <<'JSON'
{
  "version": 1,
  "minor_version": 5,
  "key": "core.config_entries",
  "data": {
    "entries": [
      {
        "created_at": "2026-11-14T12:00:00.000000+00:00",
        "modified_at": "2026-11-14T12:00:00.000000+00:00",
        "discovery_keys": {},
        "subentries": [],
        "entry_id": "nightsim_hockey_score",
        "domain": "hockey_score",
        "title": "Hockey Score — Night Sim",
        "data": {"url": "http://director:5959", "api_key": "test-key"},
        "options": {},
        "version": 1,
        "minor_version": 1,
        "pref_disable_new_entities": false,
        "pref_disable_polling": false,
        "source": "user",
        "unique_id": "http://director:5959",
        "disabled_by": null
      }
    ]
  }
}
JSON

cp -r "$ROOT/custom_components/hockey_score" "$NS/config/custom_components/"

# --- the director (scripted fake API), as a container on the sim network ---
docker run -d --name "$DIRECTOR_CONTAINER" \
  --network "$NETWORK" --network-alias director \
  -v "$ROOT":/repo:ro -v "$NS":/log \
  --entrypoint python3 "$IMAGE" \
  /repo/tests/director.py --port 5959 \
    --scenario "/repo/tests/scenarios/${SCENARIO}.json" \
    --log /log/director.jsonl --key test-key >/dev/null

director_up() {
  docker exec "$DIRECTOR_CONTAINER" python3 -c "
import sys, urllib.error, urllib.request
try:
    urllib.request.urlopen('http://127.0.0.1:5959/team', timeout=2)
except urllib.error.HTTPError as e:
    sys.exit(0 if e.code == 401 else 1)
except Exception:
    sys.exit(1)
" >/dev/null 2>&1
}
for _ in $(seq 1 20); do director_up && break; sleep 0.5; done
director_up || { echo "director did not come up"; docker logs "$DIRECTOR_CONTAINER"; exit 1; }

# --- the quarantined HA container, on the same network ---------------------
docker run -d --name "$CONTAINER" \
  --network "$NETWORK" \
  -v "$NS/config":/config \
  "$IMAGE" >/dev/null
IP=$(docker inspect -f "{{ (index .NetworkSettings.Networks \"$NETWORK\").IPAddress }}" "$CONTAINER")
echo "scratch HA: $CONTAINER at $IP (non-production, no ports exposed)"

# --- drive & assert ---------------------------------------------------------
set +e
"$ROOT/.venv/bin/python" "$ROOT/scripts/nightsim_driver.py" \
  --host "$IP" \
  --scenario "$ROOT/tests/scenarios/${SCENARIO}.json" \
  --director-log "$NS/director.jsonl"
RC=$?
set -e

if [ "$RC" -ne 0 ]; then
  echo "=== integration debug log (last 40 hockey_score lines) ==="
  docker logs "$CONTAINER" 2>&1 | grep -i 'hockey_score\|config entry' | tail -40 || true
fi
exit "$RC"
