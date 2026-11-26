# FACTS

Project facts that were learned the hard way. Read before deploying.

- `deploy/rolling-restart.sh` is a dry run unless given `--apply`. Deploying = rsync + pip install + `rolling-restart.sh --apply`.
  Without `--apply` the units keep running old code; check `systemctl --user show <unit> -p ActiveEnterTimestamp`.
  (2026-11-25: D-024..D-027 sat undeployed for hours because of this.)
- The engine never re-grants energy over time. WAIT gives +2 energy only by burning 1 carried material
  (cargo.ts applyCargoFuel); the zero/zero lockout rest needs energy 0 and a full hold.
- The Orin's IP is DHCP and changes (was .99, became .100 on 2026-11-25). `~/.ssh/config` uses `HostName linux.local` (mDNS). Host keys checked: ED25519 SHA256:1oUCQW2N…
- `NOEMA_PIN_PR_TOKEN` (Zero-State-LLC/Noema Actions secret) was reset on 2026-11-25 to the scrimshawlife-ctrl gh OAuth token (scopes: repo, workflow). Pin PRs open as that account. If `gh auth` on the Mac is refreshed or revoked, re-run `gh auth token | gh secret set NOEMA_PIN_PR_TOKEN -R Zero-State-LLC/Noema`.
- noema-client releases: bump `src/noema_client/_version.py` in a PR, then `gh release create vX.Y.Z --target main` (triggers the PyPI publish workflow). The Orin installs from PyPI: `~/noema-players/.venv/bin/pip install --no-cache-dir noema-client==X.Y.Z`.
- Noema and Noema-Specs require code-owner review; merges run with `gh pr merge --admin` under the standing merge grant. Noema-Specs CI checks the committed graft index: rebuild with `GRAFT_NO_GITIGNORE=1 npx -y @nanonets/graft@0.26.0 --dir graft build` and `git add -f graft`.
- Orin venv is `~/noema-players/.venv` (dot-venv). Deploy: rsync to `orin:noema-orin-src/`, `~/noema-players/.venv/bin/pip install --no-deps --force-reinstall .`, then `deploy/rolling-restart.sh --apply`. Restart only some units with `UNITS="noema-player@m03 ..."`. Never `pkill -f rolling-restart` over ssh: the pattern matches the ssh command itself and kills it.
- `rolling-restart.sh` UNITS takes full unit names: `UNITS=noema-player@m01`, not `UNITS=m01` (fails "m01.service not found").
- Office cleanup that the model won't land: `client.act(ActionProposal(action="ORG_OFFICE_RETIRE", ...))` with org_id/office_id args works; `run_macro("office retire ...")` does not. Retry on STALE_HEAD.
