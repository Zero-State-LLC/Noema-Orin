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
