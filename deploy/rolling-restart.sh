#!/usr/bin/env bash
# Safe one-role-at-a-time rolling restart for Noema-Orin systemd units.
# Dry-run by default; pass --apply to execute systemctl restarts.
set -euo pipefail

APPLY=0
STAGGER_SECONDS="${STAGGER_SECONDS:-15}"
if [[ "${1:-}" == "--apply" ]]; then
  APPLY=1
fi

UNITS=(
  "noema-role@founder.service"
  "noema-role@quartermaster.service"
  "noema-role@custodian.service"
  "noema-role@archivist.service"
  "noema-role@speaker.service"
  "noema-role@surveyor.service"
)

for unit in "${UNITS[@]}"; do
  if [[ "$APPLY" -eq 1 ]]; then
    echo "[rolling-restart] restarting $unit..."
    sudo systemctl restart "$unit"
    systemctl is-active --quiet "$unit"
    echo "[rolling-restart] $unit active; waiting ${STAGGER_SECONDS}s..."
    sleep "$STAGGER_SECONDS"
  else
    echo "[dry-run] would restart $unit and wait ${STAGGER_SECONDS}s"
  fi
done
