# NEXT (2026-11-28 04:55Z, latest entry at the bottom)

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

## 2026-11-27 13:43Z: local_first + semantic memory fleet-wide
- All 6 agents run local_first S1 (llama-server qwen2.5-3b) with the bge-small embedder. Done early because the shared servers add almost no RAM.
- 15 min after: 0 tracebacks, embeddings m01 38 / m02 48 / m03 32 / m04 38 / m05 18 / m06 132. fleet.sh 20: m02 11/20, m03 12/20, m05 20/20. m01 is idle as before (org settled). 1.2 GB available.
- Watch: RAM floor. If available stays under 1 GB, set `NOEMA_KIOSK_RELOAD_S` lower or stop the kiosk (`sudo systemctl stop noema-dashboard-kiosk`). Rollback per agent: restore `mXX.env.bak-pre-local`.

## 2026-11-27 14:28Z: dashboard efficiency + legibility pass
- Measured on the Orin. Before: kiosk WebKit 820->980 MB RSS growing, 479 s CPU per 10 min (about 80% of a core). Snapshot 52 KB built per viewer every 4 s, and full DOM teardown each tick.
- After: WebKit 236 MB steady, 3.1 s CPU per 2 min (about 2.6% of a core). Snapshot is cached (repeat GETs take 3-6 ms vs 300 ms). SSE frames are 13-19 KB without the map and 37 KB with it. The map hash ignores seen_seq. RAM available went from about 1.0 GB to 2.2 GB.
- The biggest single win: WebKitGTK paints in software at 4K, so the infinite halo animation and HW-compositing churn drove the CPU. The kiosk now uses HardwareAccelerationPolicy.NEVER and no infinite animations.
- Legibility: role share over the last 50 turns as a big number + sparkline + "last role action N turns ago"; feed collapses repeats (xN) with a ROLE ONLY toggle (kiosk default); alerts tiered crit/warn/expected (idle_rate muted); RAM bar warns under 1 GiB; S1/min and EMB/min chips; fanned agent pins on the map; kiosk hides operator controls.
- Known: "cost: Ollama fallbacks 1681/1525" is pre-D-075 history (last real fallback 06:19Z). It ages out of the 24h window at about 06:19Z on 11-28. No action needed.
- Merged #192 (D-078 opt-in transition log, off by default). It's your call whether to set `NOEMA_TRANSITION_LOG=1`.

## 2026-11-27 14:55Z: C3/C4 deployed, C5 canary on m06
- #204 (consequence model in shadow) and #205 (shadow accuracy in the digest/dashboard) are rolled fleet-wide: 308 tests OK, all 6 active. Both are inert unless the flags are set.
- C5 (#200) canary: m06 has `NOEMA_TRANSITION_LOG=1` + `NOEMA_CONSEQUENCE_SHADOW=1` (backup `m06.env.bak-pre-c5`). In the first 10 min: 3 rows (about 48 KB/row, because the full canonical observation is stored), 0 errors, m06 RSS 31 MB (ceiling 160M).
- Watch: bytes/row is high. At about 6 agents x 250 turns/h that is roughly 70 MB/h before gzip rotation. The rotation cap (16 MB x 32 segments) bounds it at about 512 MB per agent. Check after the 1h soak, then decide on fleet-wide enablement.

## 2026-11-27 15:05Z: approvals applied
- #5/#168 closed. G-002 is APPROVED (gate states allow only BLOCKED/NOT_COMPUTABLE/APPROVED). Receipt `docs/evidence/qualify-orin-20261127T1457Z.json`: 20.6 tok/s, embed p95 12 ms, 5.8 W. #207 and #208 merged, main CI green.
- #4: blocked on a human device-code approval at noema.guru/connect for the isolated world attach (details on #4). The client is now 0.2.0, so re-pin `official_client.py` first.
- #6: still blocked on a Noema-Specs canonical decision for spec 014 (G-001). Operator approval cannot substitute for that.
- Ship command: always `sleep 20 && gh pr checks --watch --fail-fast` and merge only on rc=0.

## 2026-11-27 15:17Z: all gated issues closed under operator approval
- #4 closed by #210 (D-081): `official_isolated.OfficialIsolatedClient` wraps noema-client 0.2.0. A real isolated-world LOOK from the Orin was ok and settled in 272 ms, receipt `docs/evidence/t4-isolated-20261127T1512Z.json`. It used the Admin-minted tester token instead of a device code.
- #6 closed by #211 (D-082) after Specs#479 (ADR-013) scoped spec 014 to a non-canonical `offline.spark.*` chamber. No Spark host is reachable, so there is no chamber run. The CLI `offline-spark` stays REFUSED until one exists.
- Parent #7 closed. Next: C5 soak result (m06), then fleet-wide enablement.

## 2026-11-27 16:02Z: C5 measured, fleet enabled (#200 closed)
- m06 1 h soak: 126 rows/h, 20.3 KB/row (2.56 MB/h per agent), RSS 43 MB, 0 errors. Shadow 31/31 correct, but every case was tn, so there is no rejection signal yet.
- `NOEMA_TRANSITION_LOG=1` and `NOEMA_CONSEQUENCE_SHADOW=1` are now in `~/.config/noema-orin/runtime-overrides.env` (backup `.bak-pre-c5`). All 6 are active.
- Next: once rejections accumulate, re-read the digest for tp/fp. Watch free RAM (1.7 GB).

## 2026-11-28 00:20Z: world-01 auto-INCIDENT recovered
- The hosted world entered INCIDENT on 2026-11-27 at about 19:30Z, right after STALE_HEAD rejections (a settlement commit failed). For about 4.7 h every mutation was blocked, and the fleet only showed "sessions ended early".
- Checked: durable head == DO (rev 45180, seq 86843, unsettled 0). Then ran `POST /v1/admin/lifecycle {"action":"recover"}`, which did a `restore` from the verified head and returned ACTIVE/HEALTHY. Revision advanced to 45195 within 4 min.
- Added a crit dashboard and digest alert: "world INCIDENT: latest session stopped on WORLD_INCIDENT". Root cause is filed upstream on Noema.

## 2026-11-28 01:47Z
- #215 (D-083: the consequence model ignores world-level failures) is deployed. Canary m03+m06 ran 4 min with 0 tracebacks, then rolled the rest. All 6 are active and the dashboard is active. 325 tests OK on the Orin.
- Root-cause fix for the 11-27 incident: Noema#984. A lost settlement race in the tempo alarm now resyncs and stays ACTIVE instead of going to INCIDENT. 3045 Worker tests pass and tsc is clean. It needs a code-owner review (BLOCKED, REVIEW_REQUIRED), and the production deploy is gated on the operator under the Noema grant.
- World ACTIVE/HEALTHY since recovery (rev 45180 to 45396+). The remaining STALE_HEAD rate is about 1 per session.

## 2026-11-28 02:57Z
- Noema#984: fixed the Codex P1 (after a lost race the tempo stayed in RESOLVE with no alarm). Contention now reopens a schedulable COLLECT that keeps the batch, and the retry commits. 5 targeted tests, 3046 suite pass, tsc clean, CI green. It still needs a code-owner review, then an operator yes for the prod deploy.
- World ACTIVE/HEALTHY at rev 45654. All 6 are running full sessions.

## 2026-11-28 03:08Z: upgrade and gap analysis
- `docs/analysis/upgrade-gaps-20261128.md`: 15 ranked gaps with live evidence. Top items: loop-break and planner oscillation (12–27% of turns, up to 33% MOVE reversals), m05 fallback MESSAGE spam (379 per 1000 turns), and m01/m04 with no role work (needs a product call). Also 3.2 GB of llama-server RAM for 0 player calls in 3 h, no push alert for crit, no log rotation, and the transition logs aren't backed up.
- Next: items 1–2 (canary m02 and m05), then 6–7.

## 2026-11-28 03:33Z: open-decisions research
- `docs/research/open-decisions-20261128.md` (engine, Specs and live evidence with file:line citations).
- **Founder idle is an Orin bug.** The engine shows the org treasury only to `OPERATE_RESOURCE_ACCOUNT` holders (`world-actions.ts:1236`). m01 holds none, so `plan_civic_contract` reads treasury 0 and never posts. Verified by replaying it on m01's live observation. Governance and COMMEMORATE wait for menu rows the engine never emits (no affordance row exists).
- Archivist: COMMEMORATE has the same dead check. New evidence appears from harvest scars (3 harvests), lore crystallization (about 20 cycles) and crime residues (12-cycle TTL).
- S19 option B is not needed: cargo fuel is still +2. m03's blocks are missing regional lots and the RECHARGE cap of 10.
- Consent (D-079 open item): strip other Players' message text and handles from transition rows at write time. Anything more needs a Specs ruling.
- Role rooms: close it (Specs reject new rooms, and the engine creates rooms only at genesis).
- Ops: llama `--ctx-size 4096 --parallel 1` (3.1 GB of its buffers are in swap), point `NOEMA_LLM_BASE` at llama-server, then disable Ollama, email crit alerts via AgentMail (the Signal container is unhealthy), re-mint tokens before about 12-24.

## 2026-11-28 04:55Z: second INCIDENT, client ok bug, D-085/D-086
- **Second world INCIDENT** from about 03:13:00Z to 03:46:50Z (34 min). Same signature as the first: `meta.status=INCIDENT` with `settlement_ok=true`, `unsettled_count=0`, and head == DO (rev 45724, seq 87829). It followed 9 STALE_HEAD rejections between 02:35Z and 02:55Z. Recovered with admin `recover` (`recover_mode: restore`), then ACTIVE and rev 45733 within 3 min. Evidence is on Noema#983. That makes two INCIDENTs in about 8 h, and **Noema#984 is still the fix, waiting on a code-owner review** (`partner-agents` or galadriel; admins don't bypass).
- **noema-client 0.2.0 reports world rejections as ok over WebSocket.** `protocol.py:285` sets ok=True whenever an observation is attached, and the Worker attaches one to every rejection (HTTP 200, body ok=false). Checked against the next observation, 144 of 386 mutating turns logged ok were refused. Client fix: **noema-client#58**, CI green and open for review. Until it ships, Orin reads the server's verdict from the frame itself (#221, `masked_rejection`).
- **m05 "MESSAGE spam" was refused, not delivered.** A MESSAGE affordance carries no text, so the engine refused every fallback MESSAGE (111 of 159 checked). D-085 (#222): scripted turns and the model never send a textless MESSAGE, SHOUT or BOARD. The gap analysis is corrected (#223).
- **D-086 (#224):** WORLD_INCIDENT, STALE_HEAD and NOT_IN_WORLD no longer count toward a persona's RSI rejection rate. Otherwise the newly visible rejections would roll back and quarantine any canary mutation during an outage.
- Deployed: m05+m06 canary at 04:31Z (m05 went from a MESSAGE every other turn to 0 in the next 10 turns), then fleet-wide at 04:53Z. 337 tests OK on the Orin.
- **Grill round 1 (Q1–Q6) is still waiting on the user:** founder menu-gap route, treasury sharing, archivist routing, consent scrub, #984 reviewer, token renewal. Round 2 is queued: alert recipient and channel, and the term "cohort" vs the glossary's "Controller group".

## 2026-11-28 05:40Z: ops slices D-087 to D-091
- **D-087 (#226):** a new CI job runs all 337 tests against the production client (noema-client 0.2.0 at `89a1fcac`; every module's SHA-256 matches the Orin venv). The job log shows `client-gated skips: 0`. The loopback proof is re-pinned to 0.2.0 (14/14 on the Orin). execplan/03 T14 is ticked.
- **D-088 (#227):** llama-server now runs one slot with `--ctx-size 4096 --parallel 1 --cache-ram 1024`. Measured: RSS 0.24 GB plus 0.44 GB swap, down from 0.74 GB plus 3.4 GB. System swap fell from 4.1 to 0.7 GB, and a probe answered in 437 ms. Backup: `~/.config/systemd/user/noema-llama-server.service.bak-pre-d088`.
- **D-089 (#227):** `noema-logrotate.timer` runs hourly. A log over 8 MB is gzipped to `.1.gz` (keep 5) and truncated in place, so open descriptors keep working. It is enabled, and the first run rotated nothing (all logs under 8 MB).
- **D-090 (#228):** Ollama is retired. The last-resort fallback uses llama-server's OpenAI route, and units order after `noema-llama-server`. `ollama.service` is disabled and stopped. The 1.93 GB blob is kept, because the GGUF is a symlink into it. Unit backups: `*.service.bak-pre-d090`.
- **D-091 (#229):** a treasury HARVEST asks only for the vault headroom. 24 of m02's 37 had been refused "vault is full": the pack-harvest sizing overrode the playbook's amount (8 at vault 61). Canary m02 since 05:35Z.
- **Another effect of the client bug:** after a refused turn, 0.2.0 hands the next decision the rejection's stripped observation (no organizations, players or services). That was 45% of m05's decisions and 15% of m02's. noema-client#58 fixes it at the source, so its review matters more than it first looked.
- Still open on the user: grill round 1 (Q1–Q6), the #984 reviewer, and a decision on noema-client#58 (or a reviewer for it).

## 2026-11-28 07:25Z: D-092, D-093 and a third INCIDENT
- **Loop-break, re-measured on labelled data.** HARVEST repeats were all vault refusals (fixed by D-091). The MOVE repeats, most INSPECT repeats and 16 of the WAIT repeats happened inside an INCIDENT window. What's left is m04 idling (29 WAIT repeats) and m05 reposting notices. So the planned HARVEST/REFINE exemption isn't supported and was dropped.
- **D-092 (#231): the storefront is where the Compact's stall stands.** m02 reversed 16 of 49 planner moves. A replay through the real playbook showed 18 of 18 inbound reversal moves came from RETURN_STOREFRONT. That rule pulled m02 to `room.civic-exchange`, which has no stall. The Compact's only stall is in `room.archive` (5 live BUY_ORDERs). The map never recorded it because the entity has a label but no `infra_type`. Changes: the map records stalls by label, `storefront_room()` locates the storefront, SUPPLY_PEER runs before the pull, and the pull to an empty storefront needs energy to list. Planner turn lines now carry `step`. Replayed: 7 of 10 reversal arrivals now SUPPLY the custodian.
- **D-093 (#232): one notice per room per world cycle.** The engine keeps one notice per room for one cycle, so 34 of m05's 130 notices only replaced the previous one.
- **Canary:** m02 and m05 run main `2b619de` (D-091 to D-093) since 07:22Z. The other members still run the code they loaded at the 05:23Z D-090 rollout (`ed76405`). D-091 changes only m02's behaviour, so they lose nothing in the meantime. Widen once the m02/m05 evidence looks clean.
- **INCIDENT 3, 07:05:43Z to 07:10:33Z.** The trigger was a settle RPC that failed on a Postgres statement timeout. The turn code was literally `canceling statement due to statement timeout`. This path, unlike #984's tempo race, goes straight to INCIDENT. The gate held (revision 46377 equal to the head, flags false, 0 unsettled), and a guarded `recover` restored the world. It advanced normally afterwards. Evidence and a proposed engine fix are on Noema#983 (comment 7235850321). Scripts: `~/.jcode/scratch/guarded_recover.py` and `overview_gate.py`.
- **Alerting:** a session-scoped watcher polls the Orin turn logs every minute for WORLD_INCIDENT and wakes the operating session. A durable push channel still waits on grill round 2 (recipient and channel).
- **Logs:** transition logs rotate into `transitions-00000N.jsonl.gz`. Analyses that read only `transitions.jsonl` undercount; m05's live segment held 1 of 130 notices.

## 2026-11-28 08:30Z: D-094, engine fix #985, and the 07:13Z transient explained
- **D-094 (#234, `5138d08`) and its amendment (#235, `eb13c57`): no fuel wait for a treasury build the menu hides.**
  - After D-092, 28 of m02's 39 planner turns were WAIT_TREASURY_BUILD_FUEL or COLLECT_BUILD_FUEL.
  - Its memory records all three build classes as built, so `prefer_builds` never offers those CONSTRUCTs and D-061 never fires.
  - The wait, the fuel run and the shared router's WAIT_BUILD_ENERGY now skip built classes.
  - Replay over m02's 49 turns since 07:22Z: those steps fall to 0.
  - On the m02 canary since 08:15:29Z, the first 10 turns were SEEK_CUSTODIAN, SUPPLY, TREASURY_HARVEST and RECHARGE, with no fuel waits and 0 refusals.
- **Open for the user:** the vault sits at 61 of 64, and the engine still offers Compact generator and storage-bay builds. Building a second one of a class is a policy call. D-061 as implemented builds each class once.
- **D-093 canary (m05 since 07:22Z):** 13 notices in 13 distinct (room, cycle) slots, so no repeats. Before the change, 34 of 130 were repeats.
- **m02's SUPPLY FORBIDDEN** was "They are not here to receive supplies" (`world-actions.ts:4910`): the custodian moved between the observation and the act. It isn't a bug (1 of 4 SUPPLYs).
- **Noema#985:**
  - A Postgres statement timeout on the player settle path now resyncs and stays ACTIVE, and the actor gets `SETTLEMENT_RETRY`. That was the INCIDENT 3 trigger.
  - Local result: 3046 tests pass and tsc is clean. CI is green.
  - Review is requested from galadriel-openclaw and partner-agents. Deploying it is the user's call.
- **The 07:13Z transient is explained** (#983 comment 7236596593).
  - Commands interleave inside the world DO across the settle `await`, because there is no mutex.
  - A late failure restores its stale pre-command snapshot over a concurrent commit, which leaves the DO sequence one behind the head.
  - A concurrent lost race's contention branch writes ACTIVE/HEALTHY and clears another command's INCIDENT with no operator recover.
  - Both reproduce on origin/main with the real DO harness. #985 removes the first one for statement timeouts.
  - Suggested to the engine owners: serialize mutating commands per DO, and don't clear an INCIDENT from the contention branch.
- **Unlabelled turns:** `client.play()` raises on a transport drop, so `record_outcomes` never runs for that session. m05 had 162 drops against 241 completed sessions, m01 81 against 311.
- **m05 idles 75% of its turns.** Once its notice slot is used, `focus` strips idle verbs and `_ask` strips the planner-only text verbs, so the model gets an empty menu. The generic fallback then INSPECTs the same entity (`relay-7`) again and again. The local model is healthy: three probes answered in about 2 s.
  - Where an idle speaker should go (a herald patrol) is the same kind of routing decision as grill Q3. It costs energy that an empty hold cannot regain without RECHARGE, so it waits for the user.
- **Rollout (verified):** a full rolling restart onto `eb13c57` (D-091 to D-094) ran from 08:27:39Z (m01) to 08:35:41Z (maint-patrol). All 7 units are active, and the dashboard was restarted (HTTP 200). A kiosk screenshot shows the live panel with UNITS 6/6 and SSE LIVE. The INCIDENT watcher stayed quiet.
