# Native Always-On Mission Control Dashboard (`D-077`)

`noema-dashboard.service` runs natively on the Jetson Orin Nano (`127.0.0.1:8787`, pure Python stdlib, `MemoryMax=96M`) and drives an attached always-on monitor via `deploy/jetson/noema-dashboard-kiosk.service`.

## Enable on Jetson Orin Nano

```bash
cp deploy/systemd/noema-dashboard.service ~/.config/systemd/user/
cp deploy/systemd/noema-player@.service ~/.config/systemd/user/
cp deploy/jetson/noema-dashboard-kiosk.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now noema-dashboard.service
systemctl --user enable --now noema-dashboard-kiosk.service
```

## Optional Auth & Remote Access

- **Dedicated attached monitor (default):** `noema-dashboard.service` binds strictly to `127.0.0.1:8787` with `NOEMA_DASHBOARD_ALLOW_LOCAL_CONTROL=1`, so the local monitor can view and run audited controls without exposing any LAN port.
- **LAN / Tailscale / Cloudflare Access:** Create `~/.config/noema-orin/dashboard.env` (`0600`) with distinct `NOEMA_DASHBOARD_READ_TOKEN` and `NOEMA_DASHBOARD_CONTROL_TOKEN` values before binding beyond loopback or pointing a `cloudflared` Zero Trust tunnel at `http://127.0.0.1:8787`. Never expose this dashboard publicly without authentication (`ADR-0002`).

## Constitutional Guardrails

- All observation SQLite opens use `?mode=ro` so the dashboard never stalls an agent turn.
- Every control call passes strict unit/member/knob allowlists and logs a secret-free record to `~/noema-players/logs/dashboard-audit.jsonl`.
- No manual in-world command submission, no token/Admin JWT viewing or minting, and no `offline-spark` toggles (`G-001`).
