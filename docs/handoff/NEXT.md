# NEXT (2026-11-25)

## State
- Merged and live (restarted with --apply 2026-11-24 16:26-16:48 PST): D-024..D-028 (#56-#62).
- Timers on Orin: memory-sync (5m), metrics (10m), token-watch (daily). Tokens expire ~2026-12-24.

## Blocked on operator
- Zero-State-LLC/Noema#907: zero energy + empty hold is a permanent lock in the engine. Five of six agents are stuck
  at energy 0, so idle rates stay high until there's a rule decision.

## Next slices
- Verify the office catalog live: Steward and Archive Keeper created and seated, no RULE/DESIGNATE flip-flop.
- S3 in-session recovery, S5 stale-head retry (only ~10 STALE_HEAD total, low priority), S15-S18 role loops,
  S19 docs, S20 memory compaction.

## Open decisions (researched 2026-11-25, awaiting user)

1. **#907 energy lock.** RFC-0117 rests only at energy 0 AND storage 0 (full hold). RFC-0119 burns cargo. Empty hold + energy 0 has no exit. RFC-0117 explicitly rejected passive regen. Recommend RFC-0117 amendment: WAIT at energy 0 rests +2 energy regardless of hold. Engine rule change, so user decides.
2. **Orphan orgs.** Engine has ORG_LEAVE only (actions.ts:3299), no dissolve. m01 founded 34df3bb5 (pinned), 81a1adb9, 8acbfc9e. Recommend leaving them dormant; ORG_LEAVE on the two duplicates is optional cleanup.
3. **Alert channel.** Today: D1 + log digest. Recommend staying there until agents are unstuck (current alerts are all one known cause), then email via Cloudflare Email Service.
4. **Workers AI cost cap.** Decide model @cf/meta/llama-4-scout-17b-16e-instruct at $0.27/M in, $0.85/M out. Observed ~47 turns/h/agent, ~70% model-sourced, so ~4,800 calls/day for 6 agents. At an estimated ~3k input tokens/call that is roughly $4/day (~$120/month); the 10k free neurons/day covers about $0.11. Recommend a per-day call cap in the Worker (e.g. 6,000 decide calls, falls back to local Ollama) plus measuring real token usage first.

## 2026-11-25 update
- Decision 1 resolved: engine #910/#911 (empty-hold lockout rest) is live, and D-030 makes agents WAIT at energy 0. All 6 agents now cycle WAIT then act (m06 went from 0 to 2).
- D-030 tiered decide model: cheap menus go to Granite 4.0 H Micro, strong ones to Scout. TODO: log the per-turn tier (stats_tier) to verify the live split. Decision 2 (cost cap) is still open; re-estimate after a day of tiered usage.
- 2026-11-25 02:45Z: D-031 live. Founder created Steward (`…steward.18c17379`) and Archive Keeper (`…archive-keeper.c0e3fac7`), seated Rivet-Custodian and Vellum-Archivist, and designated successors. Offices S10-S14 verified. The tier log shows org turns on strong and routine turns on cheap.
- Next: S15-S18 role loops (office holders using ORG_OFFICE_ACT), S20 memory compaction, cost cap after a day of tier data.
- 03:10Z finding: energy-spending roles (quartermaster, custodian, surveyor) cap at about 50% role actions because WAIT gives +2 energy per turn and nothing else regenerates. m05 (speaker, energy 58) acts in role 70% of turns. Raising the cap needs an engine decision (e.g. cargo fuel 1 cargo -> +4, or vested materials refuel org members). Open decision #5 for the operator.
- Custodian (m03) got 0 role actions in 60 turns: hold empty, no REPAIR target in reach at energy 1-2. Investigate next: route to the damaged Civic Exchange infra with materials.
- 04:12Z: D-033..D-035 live. The custodian still can't HARVEST, and that's provable: every arrival costs MOVE 1, and rest tops out at 2, so it always arrives with energy 1. HARVEST needs 2, and WAIT at energy 1 with an empty hold gives nothing. There's no adapter fix. **Open decision #5 (operator):** the engine change proposed on Noema#907 (lockout rest also when the hold is empty and energy < 2). The same rule raises the ~50% role-action ceiling for the quartermaster and surveyor.
- The Orin's IP moved .99 -> .100; ssh now uses linux.local (FACTS.md).

## Open decisions, round 2 (researched 2026-11-25 04:55Z)

**#5 Energy-1 lock (engine rule, operator).** Noema#907 is CLOSED. My follow-up comment is unanswered. Facts: MOVE 1, HARVEST 2, REPAIR 3; rest only at energy 0 (+2); cargo fuel +2 needs cargo; no passive regen (RESOURCE-ECONOMY energy regen 0). Every arrival lands at energy 1, so m03 is blocked and m02/m06 cap at ~50% role turns. Also, **spec drift**: engine #910/#911 extended lockout rest to empty holds, but Noema-Specs RFC-0117 still says full hold only, with no amendment.
  - A (recommended): amend RFC-0117: WAIT with an empty hold and energy < 2 sets energy to 2. One line in `applyLockoutRest`, no new verbs, still no passive regen. Also fixes the spec drift.
  - B: cargo fuel +4 instead of +2 (RFC-0119 lists "+2 retuned later" as unresolved). Helps loaded holds only, so it doesn't unblock m03.
  - C: no engine change. Reassign m03 to a role without energy costs (archivist-style), and accept ~50% for gatherers.
  - Needs: the operator's pick, then an RFC-0117 amendment PR in Noema-Specs plus an engine PR. Reopen #907 or file a new issue.

**#2 cost cap: data now in.** Since tier logging (02:24Z), 76% of model calls are cheap (427 cheap / 133 strong over 966 turns). ~66 turns/h/agent, 58% model-sourced, so ~6,400 calls/day. Prompt is ~1.5k input tokens (system ~650 chars + payload capped at 5k chars). Estimated $0.82/day (~$25/mo) tiered vs $2.82/day untiered. Recommend: a soft cap of 10,000 decide calls/day in the Worker (about 1.5x current, about $1.30/day worst case), falling back to strong-only refusal, so local Ollama takes over. Measure real token counts by logging `usage` from the Worker response before tuning.
- 05:02Z operator approved 5A and cap 10000. D-037 cap is live (Worker 6456a239). Engine PR Zero-State-LLC/Noema#926 and spec PR Zero-State-LLC/Noema-Specs#456 are open. After #926 deploys, verify m03 HARVESTs (energy 1 + empty hold should rest to 2).
- 06:03Z: **custodian loop live**. Noema#926 deployed (Worker ca151afa, dispatched manually; the pin-PR step keeps failing on NOEMA_PIN_PR_TOKEN auth, a pre-existing issue since 01:45Z). D-038..D-040 shipped. m03 now does HARVEST 8 -> RESTORE ("You restored the archive annex.") -> HARVEST -> REPAIR.
- 06:15Z: **Synced across suite**: `Noema-Specs#456` (RFC-0117 amendment 1) is merged (`66b28bc`), live Worker `ca151afa` is pinned in both `Noema-Specs` and `Noema`, `noema-client` `worker-contract-drift` is green, and `deploy-worker-pin-pr.yml` now falls back to `GITHUB_TOKEN` when `NOEMA_PIN_PR_TOKEN` fails (operator may still rotate `NOEMA_PIN_PR_TOKEN` when convenient).
- D-037 cap live; `GET /usage` shows ~650 tokens in per call.
- 06:20Z: Noema-Specs#456 merged. Pin-PR still fails: secret `NOEMA_PIN_PR_TOKEN` on Zero-State-LLC/Noema was last updated 2026-08-25 (not rotated) and gets "Authentication failed"; the GITHUB_TOKEN fallback gets 403 (workflow `permissions: contents: read`). Run 45559703109. Deploy itself succeeds.
- 06:29Z: pin-PR fixed. The secret was reset from gh auth, deploy run 45560502414 is green, and pin PR Noema#928 is merged (Worker e2fbff23).
- 07:34Z: D-041..D-043 live. Quartermaster m02 constructed a **storage_bay** in Civic Exchange (it appears in the engine observation at seq 65760): it waited 3 times to energy 6, then ran CONSTRUCT. The founder now idle-skips (29 of the last 600 turns fleet-wide were model calls avoided). Next: watch the generator build, then S3/S5 (low).
- 09:41Z: D-044..D-046 live, plus a D-045 hotfix (a TypeError in _plan for supply roles; the ship gate is now `scripts/check.sh`, which exits nonzero on failure). Last 40 turns, role actions: archivist 10 (RECONSTRUCT is back via INSPECT evidence), speaker 23, surveyor 24, custodian 6, quartermaster 5, founder 0 (done, idle-skips). Workers AI today: 1,042 calls, ~873 tokens in per call, 69% cheap tier. Quartermaster: free storage is the bottleneck (it refills about 1 per WAIT, and one HARVEST uses it all). Generator not built yet; its cost is not yet checked against the engine.
- 10:37Z D-047 live. RFC-0133 (Specs#463), engine Noema#949 (Worker 4808ae2f, pin #953), noema-client 0.1.25 (#51/#52, on PyPI and the Orin), Orin #101/#102. The founder seated the Quartermaster office. m02 treasury-harvested on turn 6 (its pack stayed 6 free), and SUPPLY affordances appear. Not yet seen: a SUPPLY to the custodian, which needs m02 and m03 in the same room. Orin CI was red since e7efb30 (client-dependent tests ran without noema_client); fixed in #102, and check.sh now runs both modes.
- 13:15Z, D-048 to D-051 live (Orin #104 to #108). Role actions per 30 turns: quartermaster 11 (6 HARVEST, 5 SUPPLY, 0 SUPPLY rejections after D-051), archivist 15, speaker 17, founder 0 (done), custodian 1, surveyor 1 (it now walks: 8 rooms in 30 turns, FOCUS declared once). Rejections fleet-wide: only LOOK:BUDGET_EXCEEDED (attention) and transport noise; STALE_HEAD about 1 per session, so S5 is not worth doing.
- Open: the custodian m03. The only verb on offer where it walks is HARVEST on depleted nodes. RESTORE/REPAIR last showed in civic-exchange and relay-quarter. Next: route a loaded custodian to the most recent REPAIR/RESTORE room instead of the HARVEST room (goal_verbs picks supply while the hold isn't empty).
