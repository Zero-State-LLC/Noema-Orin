# FACTS

Project facts that were learned the hard way. Read before deploying.

- `deploy/rolling-restart.sh` is a dry run unless given `--apply`. Deploying = rsync + pip install + `rolling-restart.sh --apply`.
  Without `--apply` the units keep running old code; check `systemctl --user show <unit> -p ActiveEnterTimestamp`.
  (2026-11-25: D-024..D-027 sat undeployed for hours because of this.)
- The engine never re-grants energy over time. WAIT gives +2 energy only by burning 1 carried material
  (cargo.ts applyCargoFuel); the zero/zero lockout rest needs energy 0 and a full hold.
