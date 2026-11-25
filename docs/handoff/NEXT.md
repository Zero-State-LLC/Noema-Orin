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

**S9 Treasury-funded CONSTRUCT (RFC-0133 amendment).** The vault fills (cap 64) faster than SUPPLY drains it. The quartermaster could spend vault cargo on a generator (5 cargo, raises room harvest yield) in the Compact's name.
- A (recommended): an RFC-0133 amendment lets the Quartermaster office CONSTRUCT `generator`/`storage_bay` from treasury storage. Same office gate and conflict check as HARVEST, with energy from the holder.
- B: no change. The vault is only spent through SUPPLY.

**S19 Custodian throughput (engine rule).** Measured, not guessed:
- Civic Exchange has two nodes. The salvage cache holds about 12,786 and is harvestable. The production node is at 0.9, which is the "Not enough stock" line. So stock regen is NOT the bottleneck, and node regen work isn't needed.
- The real limit is energy. REPAIR costs energy 3 + 1 cargo, and each WAIT with cargo gives +2 energy for 1 cargo. An empty hold rests only to 2. One repair therefore costs about 2 to 3 turns of waiting, and walking spends the margin.
- A (recommended): no engine change for now. Let D-053 to D-057 (stay beside work, work queue, quartermaster supply) run for a day and re-measure with `fleet.sh 200`.
- B: cargo fuel +3 instead of +2 (RFC-0119 lists the +2 value as unresolved). This raises every gatherer's ceiling.

## Next slices
- Re-measure after 24h. If m03 is still under 10% role actions, bring option B to the user.
- When the first newcomer appears, confirm a founder welcome (memory kind `welcomed`).
- The cost alarm (D-058) shows in `shared/digest.json`. Check it after a full day.
