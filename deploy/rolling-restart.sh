#!/usr/bin/env bash
# One-unit-at-a-time rolling restart for the Orin cohort (user systemd units, D-009/D-010).
# Dry-run by default; --apply restarts. Each unit must log a fresh turn before the next goes.
# Env: STAGGER_SECONDS (default 15), TURN_TIMEOUT (default 180), POLL_SECONDS (default 5), LOG_DIR,
# UNITS (space-separated override).
set -euo pipefail

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1
STAGGER_SECONDS="${STAGGER_SECONDS:-15}"
TURN_TIMEOUT="${TURN_TIMEOUT:-180}"
POLL_SECONDS="${POLL_SECONDS:-5}"
LOG_DIR="${LOG_DIR:-$HOME/noema-players/logs}"
read -r -a UNITS <<< "${UNITS:-noema-player@m01 noema-player@m02 noema-player@m03 noema-player@m04 noema-player@m05 noema-player@m06 noema-maint-patrol}"

for unit in "${UNITS[@]}"; do
  log="$LOG_DIR/$unit.log"
  if [[ "$APPLY" -ne 1 ]]; then
    echo "[dry-run] would restart $unit (user), wait for a turn in $log, then ${STAGGER_SECONDS}s"
    continue
  fi
  echo "[rolling-restart] restarting $unit"
  systemctl --user restart "$unit"
  # Count lines only now. restart returns once the old process has exited, so a turn after this point is the new
  # process's. Counted before the restart, the old process's last turn in its stop window passed the gate (D-099).
  before=$( [[ -f "$log" ]] && wc -l < "$log" || echo 0 )
  systemctl --user is-active --quiet "$unit" || { echo "[rolling-restart] $unit not active; stopping" >&2; exit 1; }
  deadline=$(( SECONDS + TURN_TIMEOUT ))
  until tail -n +"$((before + 1))" "$log" 2>/dev/null | grep -q '"turn":'; do
    if (( SECONDS >= deadline )); then
      echo "[rolling-restart] $unit took no turn within ${TURN_TIMEOUT}s; stopping" >&2
      exit 1
    fi
    sleep "$POLL_SECONDS"
  done
  echo "[rolling-restart] $unit took a turn; waiting ${STAGGER_SECONDS}s"
  sleep "$STAGGER_SECONDS"
done
echo "[rolling-restart] done"
