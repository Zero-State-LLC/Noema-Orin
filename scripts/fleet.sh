#!/usr/bin/env bash
# Fleet report (S1): per-agent role rate, MOVE/WAIT share, energy<=1 share, rooms, rejections.
# Usage: scripts/fleet.sh [TURNS=60] [--save]   Read-only; runs over ssh on the Orin.
set -euo pipefail
N="${1:-60}"
SAVE="${2:-}"
cd "$(dirname "$0")/.."
OUT=$(ssh orin "N=$N python3 -" <<'PY'
import glob, json, os, collections, sqlite3
n = int(os.environ["N"])
idle = {"LOOK", "WAIT", "INSPECT", "MOVE", "OBSERVE"}
rows = []
for path in sorted(glob.glob(os.path.expanduser("~/noema-players/logs/noema-player@m0*.log"))):
    member = path.split("@")[1].split(".")[0]
    turns, rej = [], collections.Counter()
    with open(path, errors="replace") as fh:
        for line in fh:
            if '"offered_supply"' in line:
                try: turns.append(json.loads(line))
                except ValueError: pass
            elif '"rejections"' in line:
                try:
                    for k, v in (json.loads(line).get("rejections") or {}).get("by_verb_code", {}).items(): rej[k] += v
                except ValueError: pass
    t = turns[-n:]
    if not t:
        continue
    acts = collections.Counter(d["action"] for d in t)
    low = sum((d.get("budgets") or {}).get("energy", 9) <= 1 for d in t)
    src = collections.Counter(d.get("source") for d in t)
    rows.append({"member": member, "turns": len(t), "role": sum(v for k, v in acts.items() if k not in idle),
                 "move_pct": round(100 * acts["MOVE"] / len(t)), "wait_pct": round(100 * acts["WAIT"] / len(t)),
                 "low_energy_pct": round(100 * low / len(t)), "rooms": len({d.get("room") for d in t}),
                 "model_pct": round(100 * src["model"] / len(t)), "top": acts.most_common(3),
                 "rejections": dict(rej.most_common(3))})
print(json.dumps(rows))
PY
)
python3 - "$OUT" <<'PY'
import json, sys
rows = json.loads(sys.argv[1])
print(f"{'m':4} {'role':>5} {'move%':>6} {'wait%':>6} {'e<=1%':>6} {'rooms':>5} {'model%':>7}  top")
for r in rows:
    print(f"{r['member']:4} {r['role']:>2}/{r['turns']:<3}{r['move_pct']:>5} {r['wait_pct']:>6} {r['low_energy_pct']:>6} "
          f"{r['rooms']:>5} {r['model_pct']:>7}  {r['top']}")
tot = sum(r["turns"] for r in rows) or 1
print(f"fleet role {sum(r['role'] for r in rows)}/{tot}  move% {round(sum(r['move_pct']*r['turns'] for r in rows)/tot)}"
      f"  e<=1% {round(sum(r['low_energy_pct']*r['turns'] for r in rows)/tot)}")
PY
if [ "$SAVE" = "--save" ]; then
  mkdir -p docs/metrics
  echo "$OUT" > "docs/metrics/fleet-$(date -u +%Y%m%dT%H%MZ).json"
fi
