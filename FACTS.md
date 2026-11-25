# FACTS

Project facts that were learned the hard way. Read before deploying.

- `deploy/rolling-restart.sh` is a dry run unless given `--apply`. Deploying = rsync + pip install + `rolling-restart.sh --apply`.
  Without `--apply` the units keep running old code; check `systemctl --user show <unit> -p ActiveEnterTimestamp`.
  (2026-11-25: D-024..D-027 sat undeployed for hours because of this.)
- The engine never re-grants energy over time. WAIT gives +2 energy only by burning 1 carried material
  (cargo.ts applyCargoFuel); the zero/zero lockout rest needs energy 0 and a full hold.
- The Orin's IP is DHCP and changes (was .99, became .100 on 2026-11-25). `~/.ssh/config` uses `HostName linux.local` (mDNS). Host keys checked: ED25519 SHA256:1oUCQW2N…
- `NOEMA_PIN_PR_TOKEN` (Zero-State-LLC/Noema Actions secret) was reset on 2026-11-25 to the scrimshawlife-ctrl gh OAuth token (scopes: repo, workflow). Pin PRs open as that account. If `gh auth` on the Mac is refreshed or revoked, re-run `gh auth token | gh secret set NOEMA_PIN_PR_TOKEN -R Zero-State-LLC/Noema`.
