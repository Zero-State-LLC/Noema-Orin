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
