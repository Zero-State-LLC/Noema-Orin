# NEXT (2026-11-25 22:00Z)

## State
- Live on the Orin as of 21:52Z: D-053 to D-059 (#111 to #115) plus #116 (this docs slice: notice/work-queue noise filters).
- Fleet report: `scripts/fleet.sh [TURNS] [--save]`. Snapshots go to `docs/metrics/fleet-*.json`.

| 25 turns after deploy (21:57Z) | role | MOVE% | energy <= 1 % | notes |
|---|---|---|---|---|
| m01 founder | 0 | 28 | 0 | No newcomers met yet, so 0 welcomes (D-056) |
| m02 quartermaster | 9 | 36 | 28 | SUPPLY 5 (was HARVEST/SUPPLY 12/60) |
| m03 custodian | 3 | 40 | 20 | Was 2/60. REPAIR in relay-quarter is blocked on materials (work queue) |
| m04 archivist | 10 | 12 | 24 | RECONSTRUCT 6 + PUBLISH 4. Was 0 RECONSTRUCT and 78 PUBLISH (D-055) |
| m05 speaker | 15 | 28 | 60 | Notices now planner-only, one per new fact (D-059) |
| m06 surveyor | 2 | 36 | 16 | Was 0/60 with 67% at energy <= 1 (D-053 floor) |
| fleet | 39/150 (26%) | 30 | 25 | Baseline 21:22Z: 74/360 (21%), MOVE 40, energy <= 1 40 |

## Cancelled
- S16 in-session recovery: the last 15 sessions per agent all ended `duration_elapsed`. The circuit_breaker and validation stops in the logs came from old builds.

## Open decisions (user)

**S9 Treasury-funded CONSTRUCT: APPROVED 2026-11-25 (A), D-061, Specs#467, Noema#957.** The vault fills (cap 64) faster than SUPPLY drains it. The quartermaster could spend vault cargo on a generator (5 cargo, raises room harvest yield) in the Compact's name.
- A (recommended): an RFC-0133 amendment lets the Quartermaster office CONSTRUCT `generator`/`storage_bay` from treasury storage. Same office gate and conflict check as HARVEST, with energy from the holder.
- B: no change. The vault is only spent through SUPPLY.

**S19 Custodian throughput: APPROVED 2026-11-25 (A, no engine change; re-measure at 24h).** Measured, not guessed:
- Civic Exchange has two nodes. The salvage cache holds about 12,786 and is harvestable. The production node is at 0.9, which is the "Not enough stock" line. So stock regen is NOT the bottleneck, and node regen work isn't needed.
- The real limit is energy. REPAIR costs energy 3 + 1 cargo, and each WAIT with cargo gives +2 energy for 1 cargo. An empty hold rests only to 2. One repair therefore costs about 2 to 3 turns of waiting, and walking spends the margin.
- A (recommended): no engine change for now. Let D-053 to D-057 (stay beside work, work queue, quartermaster supply) run for a day and re-measure with `fleet.sh 200`.
- B: cargo fuel +3 instead of +2 (RFC-0119 lists the +2 value as unresolved). This raises every gatherer's ceiling.

## Next slices
- Re-measure after 24h. If m03 is still under 10% role actions, bring option B to the user.
- When the first newcomer appears, confirm a founder welcome (memory kind `welcomed`).
- The cost alarm (D-058) shows in `shared/digest.json`. Check it after a full day.

## 2026-11-25 22:45Z: treasury construction live
- Specs#467 merged, then engine Noema#957 deployed as Worker b7ca6c7c (pin #958 merged), then Orin #117 (D-061) and #118 (D-062) live.
- Live: m02 sees "Build a generator for Reach Compact" with the vault at 36. The build hasn't happened yet: the generator costs the holder 8 energy and m02 runs at energy 1 to 3. With an empty hold WAIT rests only to 2, and cargo fuel gives +2 per cargo. This is the same energy ceiling as S19.
- Check after 24h with `fleet.sh 200`, together with the custodian. If no treasury build has happened, the S19 fallback (cargo fuel +3) or a lower holder fuel share is the user's call.

## 2026-11-26 00:22Z
- D-066 incident closed: 22 duplicate Notice offices retired by operator script; home org = 4 offices, all occupied. D-067 (#124) deployed: fallback no longer picks planner-only verbs.
- Next: watch m01 for zero creates; m02 first treasury build; 24h re-measure with `fleet.sh 200 --save` (custodian energy decision, fallback cargo fuel +3).

## 2026-11-26 04:05Z
- D-068 (#126) deployed to m01: the generic fallback's MESSAGE (183 sends since D-067) now becomes WAIT. Zero office creates since the 00:22Z deploy; home org still has 4 offices.
- m02: 2 treasury CONSTRUCTs landed (energy 9->1, `built` facts include generator and storage_bay). Vault is 29.
- Due ~2026-11-27 00:00Z: `fleet.sh 200 --save` custodian-energy re-measure. Fallback plan: cargo fuel +3.

## 2026-11-26 04:36Z
- D-068 verified live: 0 MESSAGE sends, 0 office creates since restart.
- D-069 (#128) deployed to m06: the surveyor now walks (MOVE east/east/south/east after restart). Before: 0/100 role actions, 67% WAIT at energy 80.
- fleet.sh 100 at 04:27Z: role 98/600. m01 has 0 role actions but is correctly idle (org settled). m05 shows MESSAGE 32, which is the speaker doing its role.
- Still due ~2026-11-27 00:00Z: `fleet.sh 200 --save` custodian-energy re-measure.

## 2026-11-26 11:48Z: #130 rolled fleet-wide
- #130 (RSI ratchet, Deep Time Atlas, RFC-0136 RECHARGE, new resident verbs) passed 201/201 on Orin. D-066..D-069 guards intact.
- Canary m03+m06 ran 7 min with no errors (m06 RECHARGE x3), then rolled m01/m02/m04/m05. All 6 active and taking turns.
- Watch (next 24h): SHOUT/BOARD/CONTRACT_POST/COMMEMORATE are model-choosable, not planner-gated. If any agent repeats one more than about 5 times per session, gate it like D-059 (one per fact).
- Watch: RSI autonomous rollback writes `quarantine.jsonl`; `metrics.py` raises `rsi_rollback` alerts.
- Due ~2026-11-27 00:00Z: `fleet.sh 200 --save` custodian-energy re-measure. RECHARGE may change the answer.

## 2026-11-26 12:30Z
- 20-min watch after #130: 0 SHOUT/BOARD/CONTRACT_POST/COMMEMORATE/ATTEST/GOVERNANCE across all 6 agents, so no spam. No quarantine.jsonl and no rsi_rollback alert yet.
- D-070 (#132) deployed to m04: supersede churn (15/30 turns, 103 canned relay-7 revisions) is now one per subject. Verified: 2 supersedes on 2 distinct subjects (relay-7, scar-conduit).
- m05 is mostly fallback MOVE (16/29) and m03 is mostly idle. Look at these next if the 24h numbers stay flat.
- Due ~2026-11-27 00:00Z: `fleet.sh 200 --save` custodian-energy re-measure.

## 2026-11-26 13:14Z
- D-071 (#134) rolled to all 6: the generic fallback is held to the role allow list. m05 had fallen back to ORG_MEMBER_REMOVE x4 and ORG_OFFICE_VACATE x2 on its own Notice office. Checked: still a member, and all 4 offices are OCCUPIED.
- m05's remaining weakness: 209/400 turns are fallback MOVE because notices are planner-gated (one per fact). That is expected, but the speaker wanders. Option: have it idle (WAIT) at civic-exchange instead. Low priority.
- Due ~2026-11-27 00:00Z: `fleet.sh 200 --save` custodian-energy re-measure.

## 2026-11-26 14:25Z: Wave 4 (#136, #137) rolled
- Orin noema-client upgraded 0.1.25 -> 0.2.0 (#136 needs ClientPolicy; 1 test failed on 0.1.25). 211 tests OK on 0.2.0, and live observe works.
- Canary m02+m06 ran 8 min with no tracebacks (m02 did a treasury CONSTRUCT), then rolled m01/m03/m04/m05.
- Watch: shop_planner (stall stocking/listing, equipment upkeep) and the RSI `unequipped_broken_tool_turns >= 12` rollback.
- Due ~2026-11-27 00:00Z: `fleet.sh 200 --save` custodian-energy re-measure.

## 2026-11-27 00:25Z: 24h re-measure
- `fleet.sh 200 --save`: role 211/1200 (was 98/600 at 100 turns). All 6 active, 0 tracebacks, no rsi_rollback.
- Custodian (m03): 82/200 role actions with REFINE 37, and energy <=1 on only 1% of turns. The energy shortage is resolved by RECHARGE and D-063..065, so the fallback plan (cargo fuel +3) is not needed. Closed.
- D-072 (#139) deployed to m01: AGREEMENT_FORM went from 46/200 (mostly NOT_COLOCATED) to 1 per party. Verified: 1 attempt after restart.
- m06: energy <=1 on 32% of turns, idle WAIT with an empty hold. That WAIT refuels it, so it is slow but working. Could RECHARGE-route it.
- m04: 8/200 role actions, mostly WAIT/INSPECT after D-070. Needs a new subject source.
- m02: TRADE 12 (shop) with 1 BUDGET_EXCEEDED. Shop is live.

## 2026-11-27 02:16Z
- D-073 (#141) + D-073b (#142) deployed to m04: published records no longer hold it in place, and evidence INSPECTs skip published subjects. After restart: 5 rooms in 21 turns, 4 role actions (RECONSTRUCT x2, PUBLISH, SUPERSEDE). Before: 1 room and 0 role actions.
- Next candidate: m06 RECHARGE-routing (energy <=1 on 32% of turns).

## 2026-11-27 03:13Z
- D-074 (#145) rolled fleet-wide: low energy with no RECHARGE in the room now walks to the generator room. 25 min after: 0 turns at energy <=1 fleet-wide (m06 was 32%), and m06 did HARVEST 14/20. All 6 active, 0 tracebacks.
- m04 is back to WAIT 12/MOVE 11 with no role actions in this window. Watch: it may have exhausted subjects within reach.
- **Needs user:** PR #144 (AGENTS.md state machine, by scrimshawlife-ctrl) asks to "confirm before we enforce direction" on the G-gate lifecycle order. CI is green and there are no runtime changes. Left open for you.

## 2026-11-27 03:17Z
- #144 merged (recommendation: states-only gate checks, enforce direction later once a G-gate actually moves). `machine.py check` and `docs.py check` OK on main.
- m04 idle is correct world state: all 13 inspectable subjects in reach are published, and its idle turns are planner WAIT/MOVE with no model calls, so they cost nothing. It resumes when new entities or structures appear (m02 builds, m03 repairs). A possible later slice is to allow a re-revision when an entity's condition changes. That needs a condition-change signal, so it is not urgent.
- Fleet healthy: 0 turns at energy <=1, 0 tracebacks, no open PRs.

## 2026-11-27 07:01Z
- New merged PRs #148-#150 (agents docs machine sync, gates D-009..011) are docs only, with no runtime impact and no roll needed.
- D-075 (#151) rolled fleet-wide: the "Ollama fallbacks 140%" alert was a metric bug, since scripted fallback turns were counted as local-model calls. First full sessions after: ollama_fallbacks = 0 on all 6 (Workers AI calls 0-22 per session). The 24h alert clears as old rows age out.
- fleet.sh 200 at 06:17Z: role 232/1200 (was 211). m06 63/200 (was 10) after D-074.
- idle_rate alerts (0.68-0.93) count WAIT/LOOK/MOVE as idle. That is expected given energy-limited roles, not a fault.

## 2026-11-27 08:36Z
- #153 (close SQLite connections in memory_sync/metrics) was merged at 07:29Z but not deployed. Now rolled fleet-wide: 220 tests OK on Orin, all 6 units restarted 08:27-08:34Z, 0 tracebacks.
- fleet.sh 30 right after: role 47/180. m03 REFINE 7 + REPAIR 6. m05 MESSAGE 15. m01/m04 idle, which is expected (org settled, subjects published).
- Watch: m06 shows energy <=1 on 40% of turns in this short window (it was 0% after D-074). The window spans the restart, so re-check with `fleet.sh 100`. If it stays above 20%, look at the D-074 generator-walk path.

## 2026-11-27 08:57Z: D-076 Phase 1 (#169) rolled fleet-wide
- 241 tests OK on Orin from new source. Canary m03+m06 ran 8 min with 0 tracebacks (m06 used FOCUS). Then rolled m01/m02/m04/m05.
- fleet.sh 20 after: role 40/120, energy <=1 on 7%, 0 tracebacks in the player logs. Note: `journalctl --user` has no journal on Orin. Grep `~/noema-players/logs/noema-player@mXX.log` instead.
- Open PRs: only Noema#937 (x402 plan, external author). Its review holds merge on an RFC-0120 conflict and the Noema-Specs `external_crypto_economy` DEFERRED status. Lifting that deferral is a product decision for the user, so it stays open.
- Next: watch the D-076 verbs (SELL_OFFER, CORE_SWAP, contracts, COMMEMORATE) for spam over 24h. Phase 2 (T8-T11) is ready-for-human until Phase 1 soaks.

## 2026-11-27 09:20Z: Phase 2+3 (#171, #172) rolled fleet-wide
- 255 tests OK on Orin. Canary m03+m06 ran 7 min with 0 tracebacks, then rolled m01/m02/m04/m05/maint. All 6 active, 0 tracebacks.
- Inference is still `cloud_first`: `NOEMA_INFERENCE_MODE` is unset and no llama-server unit is installed. The T10 local-first switch, T12 TRT embedder and T14 qualify run all need the physical board setup in `deploy/jetson/` (model download, unit install). That is the next hands-on slice.

## 2026-11-27 10:26Z: open-decision research + local S1 canary
- Noema#937 (x402): research posted on the PR. Noema-Specs COMPLEXITY-DOCTRINE has a "Future-economy hard deferral" that lists x402, USDC and wallets, the PSR campaign repeats it, and paying agents need `third_party_agent_compatibility_at_scale` (BLOCKED on PSR-1, Specs#363 open). It stays parked. Unblocking needs a superseding direction packet from the owner after PSR-1.
- T10 live as a canary: llama-server (CUDA) runs as `noema-llama-server` (enabled, 3.3 GB RAM still free). Only m06 is `local_first`, from 10:14Z. 0 tracebacks. Model calls are rare (most turns are planner), so the server has seen few requests.
- Next: after about 2h, compare m06 `local_s1_calls` and role% against cloud. If it's clean, add local_first to m03/m05 (m05 is the heaviest model user at 45%). Rollback is to restore `m06.env.bak-pre-local` and restart.

## 2026-11-27 11:29Z: local S1 on m03/m05/m06
- m06 ran local_first for 75 min: 0 tracebacks, local_s1_calls 13, and llama-server predicted 413 tokens in total. Model calls are rare because about 80% of turns are planner/idle_skip/fallback, so the cost saving is small but real.
- Added m03 and m05 at 11:06Z. After 20 min: 0 tracebacks, m05 role 20/20, m03 12/20, 3.2 GB RAM free.
- Next: if it's clean after about 6h, add m01/m02/m04 (backups are `mXX.env.bak-pre-local`). Phase 3 T12 (TRT embedder) and T14 (qualify, closes #5 / G-002) remain. T14 can run now that llama-server exists: `python -m noema_orin.qualify`.

## 2026-11-27 11:31Z: #5 qualification receipt (OBSERVED)
- Fix: `jetson_telemetry.py` hardcoded hwmon0/1 and an older GPU load path. On this board (Orin Nano Super, L4T R39.2.2) the INA3221 is hwmon4 and GPU load is at `bus@0/17000000.gpu/load`. With the fix, power reads VDD_IN 6.1 W and the receipt is OBSERVED.
- Receipt `docs/metrics/qualify-20261127T1130Z.json`: llama-server qwen2.5-3b Q4_K_M at 21.9 tok/s, prompt 290 ms, MAXN_SUPER, 3.1 GB available with 6 agents running.
- Still NOT_COMPUTABLE: model_load_s, embed_p95_ms (T12 TRT embedder not built), command_latency_ms. #5 stays open (HOLD, human closes it).

## 2026-11-27 11:46Z: T12 semantic memory canary (m06)
- `noema-embed-server` (bge-small f16 via llama.cpp, #178) is enabled. Qualify receipt now has embed_p95_ms 21.6.
- m06 has `NOEMA_TRT_EMBED_URL` since 11:35Z: 34 facts embedded and 0 tracebacks fleet-wide. fleet.sh 15: role 37/90.
- RAM: 2.5 GB available with both servers and 6 agents running. Don't add a bigger model. Widen the embedder and local_first to the other agents (each agent process is small) only if available RAM stays above 1.5 GB.
- Widening check is due about 17:30Z: m01/m02/m04 local_first, embedder on m03/m05.

## 2026-11-27 12:17Z: D-077 always-on dashboard merged (#186, ready to deploy on Orin)
- Merged on `main` (`bb6db3f`, PR #186, closes #180-#185): stdlib HTTP/SSE dashboard (`127.0.0.1:8787`, `MemoryMax=96M`, `?mode=ro` SQLite, audited controls in `logs/dashboard-audit.jsonl`, Hallmark `noema-ledger-dark` zero-build UI, Chromium kiosk unit `MemoryMax=512M`, `RsiRatchet.can_propose()` pause gate). 258 tests OK + 10/10 CI green; **not yet installed/enabled on the physical Orin**.
- Deploy to Orin (per `FACTS.md` venv `~/noema-players/.venv`): pull/rsync `main`, run `~/noema-players/.venv/bin/pip install --no-deps --force-reinstall .`, copy `deploy/systemd/noema-dashboard.service`, `deploy/systemd/noema-player@.service`, and `deploy/jetson/noema-dashboard-kiosk.service` to `~/.config/systemd/user/`, `systemctl --user daemon-reload`, `systemctl --user enable --now noema-dashboard.service noema-dashboard-kiosk.service`, then `deploy/rolling-restart.sh --apply` when ready to pick up the `noema-player@.service` override hook and `rsi.py` pause check.
- Watch on Orin: confirm `noema-dashboard.service` + `noema-dashboard-kiosk.service` (Chromium on `DISPLAY=:0`) keep free RAM above 1.5 GB alongside `noema-llama-server` + `noema-embed-server` (currently 2.5 GB free); verify `/usr/bin/chromium-browser` exists on L4T R39.2.2 (adjust `ExecStart` if binary is `chromium`).
- Heads-up on `runtime-overrides.env`: `noema-player@.service` loads `runtime-overrides.env` *after* `%i.env`. Leaving it absent preserves the per-agent `m03`/`m05`/`m06` `local_first` canary in `mXX.env`; clicking "Save Runtime Overrides" in the UI sets `NOEMA_INFERENCE_MODE` / `NOEMA_GROUNDED_VOICE` fleet-wide on next restart.
- Optional small follow-up: add `noema-embed-server` (#178) to `ALLOWED_UNITS` in `src/noema_orin/dashboard/controls.py` so the embed server appears in the dashboard's Infrastructure Units strip.

## 2026-11-27 12:45Z: D-077 dashboard installed on Orin
- `noema-dashboard` is enabled and serves 200 on :8787 with a live snapshot (world_seq 84400). The kiosk is skipped because the Orin is headless with no Chromium. Use an ssh tunnel (see FACTS).
- Fix: `test_dashboard` d1 read the real Orin sysfs (GPU 0.0 overrode the fixture's 38.0) after #177. The reader now takes `sysfs_probe` and the test is hermetic. `noema-embed-server` was added to ALLOWED_UNITS. 260 tests OK on Orin.
- New player unit (runtime-overrides.env hook, MemoryMax=160M, about 40-52 MB per agent observed) rolled fleet-wide.
- Merged Specs#477 (docs, watch D8 pass 4) under the merge grant.
- Soak 11:46-12:41Z: 0 tracebacks, m06 has 93 embedded facts, 2.4 GB available. Widening local_first/embedder is still due about 17:30Z.

## 2026-11-27 13:07Z: dashboard diagnosed and fixed on Orin
- Stream replayed history: the SSE feed started each log at byte 0, so viewers saw ORG_CREATE turn 1 from days ago. It now starts at EOF. Offsets were shared across viewers, so two tabs split events between them. Each connection now has its own offsets (test updated).
- MODE showed cloud_first while m03/m05/m06 run local_first. The snapshot now has per-agent `inference_mode` and `semantic_memory` read from mXX.env (only those keys, no token leak, checked). Cards show LOCAL/EMB badges and the header shows `local_first 3/6`.
- Layout: the header clipped PWR/RAM/S1/JWT and the brand text wrapped over 5 lines, and agent cards overlapped in a fixed 3-row grid. The header now wraps, the brand is one line with a humanized org name, and the grid is min-content and scrollable. LOCAL S1 shows "idle" instead of 0 t/s (llama.cpp's gauge is per interval). embed-server is in the infra strip.
- Verified in a browser over `ssh -L 8787` with live data. 260 tests OK on Orin.

## 2026-11-27 13:22Z: dashboard live on the Orin's monitor
- Cause: no graphical session (multi-user.target, gdm disabled) and the #186 kiosk unit needs Chromium, which is not installed. The kiosk was never installed, so the monitor showed nothing.
- Fix: a system unit runs xinit + `deploy/jetson/kiosk.py` (WebKit2GTK, already on the image) on vt1, enabled at boot. Verified from a capture of :0 that the full dashboard is live at 3840x2160.
- Embed server unit trimmed (`-b/-ub 512 -np 1`). RAM is about 1.5 GB available with all services up.
- Widening at about 17:30Z goes ahead regardless of RAM (shared servers): m01/m02/m04 local_first, embedder on m03/m05.
