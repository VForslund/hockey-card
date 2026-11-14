#!/usr/bin/env bash
# Capture a frozen /team (or /team/static) snapshot as a test fixture.
#
# Usage:
#   API_KEY=<the hockey-api key> ./scripts/capture_fixture.sh idle_vik_ot
#   API_KEY=... ./scripts/capture_fixture.sh static_badges /team/static
#
# URL defaults to a local hockey-api instance; override with URL=... .
# Volatile fields (last_polled_at, last_updated) are stripped so fixtures
# stay deterministic. The key is read from the environment only.
set -euo pipefail

name="${1:?usage: capture_fixture.sh <fixture-name> [/team|/team/static]}"
path="${2:-/team}"
url="${URL:-http://127.0.0.1:2070}"
: "${API_KEY:?export API_KEY first (the hockey-api key)}"

out="$(cd "$(dirname "$0")/.." && pwd)/tests/fixtures/${name}.json"
tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT

curl -sS -m 10 -H "Authorization: Bearer ${API_KEY}" "${url%/}${path}" -o "${tmp}"
python3 - "${tmp}" "${out}" <<'EOF'
import json
import pathlib
import re
import sys

src, dst = sys.argv[1], sys.argv[2]
data = json.loads(pathlib.Path(src).read_text())
for volatile in ("last_polled_at", "last_updated", "standings_updated"):
    data.pop(volatile, None)
out = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
# The badge-mirror host is deployment-private: replace it with a neutral
# one so committed fixtures never carry the real location.
out = re.sub(r"https?://[^\s\"/]+/badges/", "https://badges.example.com/badges/", out)
pathlib.Path(dst).write_text(out)
print(f"wrote {dst}")
EOF
