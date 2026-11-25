#!/usr/bin/env bash
# D-030: ask Jev which decide-model tier each world verb needs. Update model_tier.CHEAP from the output.
set -euo pipefail
dest=$(mktemp); trap 'rm -f "$dest"' EXIT
cat > "$dest" <<'J'
{"cheap": "routine, low-stakes, reversible game action: gather, rest, focus, repair, move, look; a wrong pick costs one turn",
 "strong": "consequential or social game action: org offices, succession, membership, new construction, publishing, vesting, attesting, sharing, messaging; hard to undo or affects others"}
J
for v in "$@"; do
  echo "{\"task\":\"An autonomous game agent must choose whether to perform the world verb $v this turn.\"}" |
    jev route-to --destinations "$dest" --fallback strong |
    python3 -c "import sys,json;d=json.load(sys.stdin);print('$v',d.get('pick'),d.get('confidence'))"
done
