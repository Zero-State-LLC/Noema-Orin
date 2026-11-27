# `SPEC-DASHBOARD`: Native Always-On Mission Control Dashboard (`D-077`)

**Status:** Accepted (`D-077`, 2026-11-27)  
**Design System:** Hallmark `noema-ledger-dark` Workbench (`.hallmark/log.json`, aligned with `Noema-Specs/docs/VISUAL-DESIGN.md`).

## Problem Statement

Operating the 6-agent `Noema-Orin` resident system fleet (`m01`–`m06` + `reach-maint3`) plus local CUDA `llama-server` on an 8GB Jetson Orin Nano currently requires SSH sessions (`scripts/fleet.sh`, `systemctl --user`, manual SQLite/log tailing). Operators need a dedicated, always-on monitor cockpit running natively on the Orin Nano that makes fleet health, world topology, storefront economy, cognition/RSI state, hardware headroom, and safe audited controls visible and actionable at a glance without consuming precious unified GPU RAM.

## Solution

Deliver a native, pure-Python stdlib HTTP + SSE dashboard daemon (`python3 -m noema_orin.dashboard`, `MemoryMax=96M`) paired with a zero-build Hallmark `noema-ledger-dark` Mission Control UI (`src/noema_orin/dashboard/static/`) and a native kiosk monitor systemd unit (`deploy/jetson/noema-dashboard-kiosk.service`).

## User Stories

1. As an operator watching the dedicated Orin monitor, I see live `6/6` fleet liveness, world head `seq`, inference split (`planner` / `local_s1` / `workers_ai` / `fallback`), Orin GPU/temp/power/RAM/`tok/s`, and JWT expiry countdowns without scrolling.
2. As an operator, I see each resident agent's room, budgets (`energy`, `attention`, `compute`, `storage`), `last_playbook_state`, active `AgendaStep`, dual `held_tracks`, equipment condition, 24h role rate, `stale_head_rate`, and RSI canary status.
3. As an operator, I inspect a live SVG Perihelion Reach topology map (`shared/map.db`) showing agent positions, harvest pressure, scars, damaged infrastructure, active `cohort_claims`, plus the `barter_stall` storefront listings and `WS06` contracts ledger.
4. As an operator, I drill into any agent to inspect `persona.vN` lineage, trait seed-tether bars, `agenda.json`, searchable FTS5 `memory.db` facts and relations, and `quarantine.jsonl`.
5. As an operator with control auth, I safely start/stop/restart allowlisted units, trigger `noema-players.target` group stop or canary/full rolling restart, toggle `NOEMA_INFERENCE_MODE` and `NOEMA_GROUNDED_VOICE`, tune `KNOB_SPECS`-clamped knobs, roll back or pause RSI, release stuck `cohort_claims`, and run bounded ops (`metrics`, `memory_sync`, `compact_map`, `qualify`), with every action recorded in `logs/dashboard-audit.jsonl`.

## Implementation Decisions

- **Pure stdlib backend (`src/noema_orin/dashboard/`):** `state.py` (read-only `?mode=ro` SQLite + incremental JSONL log tailer), `controls.py` (injectable `SystemdRunner` + strict allowlists + atomic `0600` writes + audit log), `server.py` (`ThreadingHTTPServer` + SSE `/api/stream` + dual read/control token auth).
- **Zero-build Hallmark `noema-ledger-dark` UI (`src/noema_orin/dashboard/static/`):** Official NOEMA chamber tokens (`#0E1114`, `#161B20`, `#E8E4DC`, `#3DDCFF`, `#C6FF3D`, `#FFB020`, `#FF4D2E`, `#9B6DFF`, `#C4A882`), one cyan primary CTA per surface, zero `innerHTML` with untrusted strings, one-shot cyan turn-arrival edge pulse, kiosk anti-burn-in micro-drift, automatic SSE reconnect.
- **Native monitor deployment:** `deploy/systemd/noema-dashboard.service` (`127.0.0.1:8787`, `MemoryHigh=64M`, `MemoryMax=96M`), `deploy/jetson/noema-dashboard-kiosk.service` (Chromium kiosk with memory-capped flags), and optional `runtime-overrides.env` sourced by `noema-player@.service`.

## Testing Decisions

- Synthetic temp `noema-players/` fixture tests covering `state.py` (`?mode=ro`, zero secret leakage), `server.py` (loopback HTTP/SSE + 401/403 auth), `controls.py` (adversarial rejection of non-allowlisted units, out-of-range knobs, shell metacharacters, concurrent restarts, read-only token escalation), static UI safety (zero `innerHTML`, Hallmark tokens present), and systemd unit hardening.

## Out of Scope (Constitutional Hard Prohibitions)

- Manual in-world `ActionProposal` injection or bypassing `ClientPolicy` / `DENY_ALWAYS` / `_hidden_verbs()`.
- Viewing, editing, or minting controller tokens or Admin JWTs.
- Enabling or toggling `offline-spark` (`G-001`) or coupling private cognition (`ADR-0002`) to public `/watch`.
