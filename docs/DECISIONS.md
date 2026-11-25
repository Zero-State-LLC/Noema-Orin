
## D-030 Depleted agents WAIT, and the decide model is picked by tier

- **Energy.** Engine #910/#911 (merged and live 2026-11-25) extends RFC-0117 lockout rest to energy 0 with an empty hold. The planner and the loop-breaker now WAIT whenever energy is 0. Before this, m06 looped FOCUS/LOOK at energy 0 and never got the rest.
- **Model tier.** Each turn's menu gets a tier. If every option is routine and reversible (LOOK/WAIT/MOVE/HARVEST/REPAIR/FOCUS/RESTORE and the COMMIT.* forms), the Worker uses `CHEAP_DECIDE_MODEL`, default `@cf/ibm-granite/granite-4.0-h-micro` at $0.017/M in (about 16x cheaper; returned correct JSON 3/3 on a probe, Gemma 4 returned empty text; llama-3.1-8b-fp8 was deprecated 2026-11-20). The Worker falls back to strong on any cheap-model error. If any social, org or build verb is offered, it keeps Scout at $0.27/M in. The verb verdicts came from `jev route-to` (scripts/jev_tier.sh) and are frozen in `model_tier.CHEAP`, so there's no Jev call per turn. Jev picks below 0.7 confidence went to strong. llama-3.2-3b was skipped: deprecation was scheduled for 2026-11-20.

## D-031 Retarget office creates before the planner dedup

After Notice existed, `planner.refine` dropped the engine's only create option (`name="Notice"`) as a duplicate before `offices.retarget_create` could rewrite it to Steward or Archive Keeper. So the founder was never offered the missing offices. `_menu` now retargets first. Regression: `tests/test_offices.py::MenuPipelineTests`.

## D-032 Harvest in bulk

The engine's HARVEST affordance always says `amount 1`. HARVEST costs a flat 2 energy, and WAIT turns 1 cargo into 2 energy, so harvesting one unit at a time only breaks even. m02 cycled HARVEST/WAIT at energy 1 to 3 for hours. The adapter now sets amount = min(8, free storage, visible stock). One harvest then fuels several WAITs (+2 energy each) and gives materials for repair and build. Holding 8 cargo costs +1 per MOVE, which one WAIT more than covers.

**D-032 correction (live, 2026-11-25 03:10Z).** Energy doesn't improve. WAIT refuels a flat +2 per WAIT whatever the cargo, and m02's hold was already full, so steady state stays at about one WAIT per 2-energy action. Bulk harvest still fills empty holds faster (custodian supply for REPAIR/CONSTRUCT), so it stays. The role-action ceiling of about 50% for energy-spending roles is an engine economy property (RFC-0117/0119), not an adapter bug. Raising it means an engine rule change (operator decision).

## D-033 Don't WAIT for energy that WAIT can't give

At energy 1 with an empty hold, engine WAIT restores nothing: lockout rest needs energy 0, and cargo fuel needs cargo. The planner still WAITed "for energy" there, then the loop-breaker MOVEd, so the custodian spent about 50% of its turns on no-op WAITs and never reached a role action. `_starved_for_attention` now counts energy only when WAIT actually refuels.

## D-034 Walk toward the goal when WAIT can't refuel

At energy 1 with an empty hold and no role verb here, the planner now spends the 1 energy MOVEing toward the goal room. It arrives at 0 and gets lockout rest (+2) there. Before this, the loop-breaker sent it the wrong way. That still leaves the in-room case: at energy 1 in the harvest room, HARVEST needs 2, and nothing burns 1 without leaving. The proper fix is an engine change (Noema#907 follow-up comment, operator decision).

## D-035 Stay where the role verb lives

D-034 live showed the custodian arriving at Civic Exchange (the only HARVEST room) at energy 1. HARVEST wasn't affordable, so `has_role_verb` (available options only) said "not here", and D-034 walked it straight out again. A room now counts as the goal if it advertises the role verb at all. The agent stays, the next turn burns to 0 or rests, then it acts.

## D-036 (S20) Memory compaction at session end

After each session, `Memory.compact()` keeps only the newest "<node> holds N <res> available to harvest" reading per (room, node, resource) and drops stale facts beyond the newest 50. Failures are logged as `memory_compacted: -1` and never end the loop. Dry run on a copy of live m02: 218 -> 103 facts, and recall still returns the latest stock reading.

## D-037 Soft daily cap on decide calls, with real token accounting

Operator-approved 2026-11-25 ("cap 10000"). The Worker counts `/chat` calls per UTC day in D1 `ai_usage`. Above `DECIDE_DAILY_CAP` (default 10,000) it returns 429. The Orin treats that as a cloud failure: the breaker opens and local Ollama decides (`NOEMA_DECIDE_LOCAL_FALLBACK=1`). The Worker also records real `usage` tokens and the cheap-call share. `GET /usage` shows 14 days. First live reading: ~650 input tokens/call (estimate was 1.5k), so tiered cost is ~$0.40/day.

## D-038 Adapter follows RFC-0117 amendment 1

Noema#926 is live: WAIT at energy < 2 with an empty hold rests to 2. `_wait_refuels` now reflects that, so at energy 1 next to an unaffordable role verb, the agent WAITs (+1 net) instead of walking. D-034's walk only fires when WAIT truly gives nothing (energy 2+ with an empty hold, below a verb's cost).

## D-039 Empty-hold supply roles gather when gathering is offered

Live diagnostic (#84): the custodian had energy 50+ and an offered HARVEST in Civic Exchange, but the decide model chose MOVE every time, and the planner bounced it back out. With an empty hold and a supply verb offered, the planner now takes it directly. One harvest node in the room was empty ("Not enough stock"). The Salvage Cache was the available one.

## D-040 Loaded supply roles spend materials where a spend verb is offered

After D-039, the custodian harvested 8 and then walked past an offered RESTORE (the model chose MOVE). With materials aboard and a role spend verb offered, the planner takes it.

## D-041 The quartermaster builds with a full hold

SHARE and VEST move ownership, not cargo, and TRADE is denied, so a full hold had nowhere to go. m02 cycled HARVEST 1/WAIT. The quartermaster now gets CONSTRUCT, with role builds `storage_bay` (6 cargo, 5 energy) and `generator` (5 cargo, 8 energy). The generator also raises the room's harvest yield (engine `productionModifier`). The existing D-018 build path takes it when the hold has 6 or more aboard. TRADE stays out of its allow list (tested).

## D-042 Skip the model when no role verb is on offer

If the planner passes and the menu has no role or supply verb, the model could only pick LOOK/WAIT/MOVE/INSPECT. The adapter now WAITs without a model call (`source: idle_skip`). WAIT is free and restores budgets. Routing toward role rooms is still the planner's job (dwell >= 2), and the loop-breaker still moves after 3 identical turns. Main saving: the founder, whose governance work is done.

## D-043 Save energy for the build

Live after D-041: m02's hold was full but it never had 5 energy. Each WAIT gave +2 (cargo fuel) and the next HARVEST spent it. When a role build is blocked only on resources (not materials), the planner now WAITs. Each WAIT burns 1 cargo for +2 energy, so after ~3 WAITs, energy 6 with 13 aboard affords a storage bay.

## D-044 Idle turns walk toward the role's goal

D-042 sent idle turns straight to WAIT. With an empty hold, m02 then sat in Generator Hall (WAIT, WAIT, loop-break MOVE, repeat) and never went back to the harvest room, because the planner's dwell gate never fired. An idle turn now routes toward the goal room (supply verbs while the hold is empty) when it can afford the move, and WAITs only when there's no route. The founder (has ORG_CREATE) still WAITs (follow-up fix: the first guard keyed on `role_handles`, which every live agent has), since its raw org offers are everywhere and get filtered.

## D-045 The archivist rests attention instead of walking

After D-044, m04 had 39/40 MOVE turns at attention 0-1. Every archivist verb costs attention 2 (`COSTS.RECONSTRUCT`), so none were available, and the idle router walked it room to room, which never restores attention. Only WAIT does (+2, cap 8). The planner now WAITs when attention < 2 and the role's goal verbs cost attention.

**D-045 hotfix.** `goal_verbs` is a tuple for supply roles, and `tuple & frozenset` raised TypeError inside `_plan`. It was caught as `memory_error`, so the custodian fell back to the model with no planner guidance. Fixed with `set(goal_verbs)`. The fix shipped past a failing test because the ship gate grepped for "OK|FAILED" and exited 0 either way. The gate is now `scripts/check.sh` (`set -e`, exit status of unittest).

## D-046 The archivist inspects to make evidence

m04 still had 32/40 MOVE turns at attention 8. RECONSTRUCT is only offered for subjects with LIVE_INSPECT or archive evidence (engine actions.ts reconSubjects), and nothing was producing new evidence, so nothing was offered and it walked. With attention >= 4 and no archivist verb on offer, the planner now INSPECTs an entity it hasn't inspected in its last 12 turns. That creates the evidence the next RECONSTRUCT needs.

## D-047 The quartermaster is a seated office with treasury services (RFC-0133)

The owner asked for the quartermaster to get "its own rules" as a system agent that serves other agents. Capability attaches to the in-game office, not a system flag (a title still grants nothing). Specs#463 (RFC-0133), Noema#949 and noema-client#51/#52 add, for an OCCUPIED `OPERATE_RESOURCE_ACCOUNT` holder:
- `HARVEST acting_for` credits the treasury vault (cap 64), so a full 16-slot pack no longer stalls it.
- `COMMIT SUPPLY` hands 1..5 treasury energy or cargo to an entered Player in the same room (compute 1).

The agent side: the founder seats a "Quartermaster" office (catalog entry). Once seated, the planner first SUPPLYs 3 cargo to the custodian when it is in the room (at most once per 10 turns), then treasury-harvests up to 8. Energy SUPPLY is not automated because peer budgets are not visible. TRADE stays client-denied even though the profile carries treasury TRADE.

## D-048 Quartermaster supplies on recorded need

In 40 turns after D-047, m05 and m06 spent 25 and 22 turns at energy 1 or less, and m03 spent 9. The treasury fills with cargo only, and WAIT burns 1 cargo for +2 energy (RFC-0119), so cargo is also fuel. Each agent now records its own room, energy and free storage in shared `map.db` (`positions`; self-observed only, never inferred from others). The quartermaster SUPPLYs 3 cargo when the recipient is in the room and:
- is the custodian with fewer than 6 aboard (REPAIR/RESTORE material), or
- is a cohort peer at energy 3 or less with an empty hold (no WAIT fuel).

Still at most once per peer per 10 turns. Energy SUPPLY stays unautomated: the treasury holds no energy, because treasury harvest credits storage.

## D-049 The surveyor doesn't re-declare its held FOCUS

m06 spent 23 of 40 turns on FOCUS, alternating with loop-break MOVEs. Re-declaring the held track does nothing (engine `applyFocus` only resets `declared_cycle`), and the client's canonical view omits `focus_lines`. The adapter now remembers the track it last declared and drops that FOCUS from the menu. Other tracks stay offered. With no role verb left, the surveyor idle-skips and routes to the least-recently-seen room, which is its charter.

Investigated and left alone: the fleet's top rejection, `ORG_OFFICE_ACT:INVALID_REQUEST` (16, all m05, persona versions 24 to 27), came from sessions before the current build. The current sessions show none.

**D-049 follow-up.** Live, m06 still did 19 FOCUS in 30 turns because the model cycled through the other tracks. After the first declaration, every FOCUS is now dropped from the menu (one track per process lifetime). The surveyor walks to the least-recently-seen rooms instead.

## D-050 A loaded custodian waits for energy before walking

m03 did 0 role actions in 30 turns. It carried 3 to 6 materials at energy 1 to 5 and kept walking (2 energy per move with cargo), so it arrived unable to REPAIR (energy 3) and burned its cargo as WAIT fuel. When a supply role carries materials, has no role verb here, and is below energy 5 (one cargo MOVE plus REPAIR), it now WAITs. Each WAIT with cargo gives +2 energy (RFC-0119).

## D-051 SUPPLY is planner-only and always carries an amount

After D-050, m02 spent 20 of 30 turns on SUPPLY, and the engine rejected most of them (`SUPPLY:INVALID_REQUEST`, args without `amount`). The model picked SUPPLY affordances directly, which skipped both the D-048 need check and the amount. Fixes:
- `_proposal` defaults `amount` to 3 for SUPPLY.
- `_ask` hides SUPPLY from the model. Only the planner proposes it, and only on recorded need.

D-050 result: m03's role actions stayed low (1/30). It now waits instead of wandering, but the only work on offer in its rooms is HARVEST on depleted nodes. Next: watch whether D-048 cargo plus waiting gets it to REPAIR/RESTORE.

## D-052 Route on verbs that pick out a room

The custodian's goal verbs include CONSTRUCT, which every room offers (map.db shows CONSTRUCT in 10 rooms). `where_offered` returns the most recently seen room offering any goal verb, so a loaded custodian walked to wherever CONSTRUCT was last seen instead of the REPAIR/RESTORE rooms (civic-exchange, relay-quarter). Routing now drops CONSTRUCT/BUILD from the goal set unless nothing else is left. Same for the quartermaster.

## D-053 Walk less: nearest goal, stay beside work, explorer floor (S3-S6)

Baseline (scripts/fleet.sh, 60 turns, 21:22Z): fleet MOVE 40%, energy <= 1 for 40% of turns, role actions 74/360. Four changes:
- **Nearest goal (S5).** `where_offered(near=here)` picks the closest room by known exits, with recency as the tie-break. It used to pick the most recently seen room anywhere.
- **Offers go stale (S4).** `observe` deletes offers a room no longer advertises. Offers that are only budget-blocked (energy, attention, materials) still count as work in the room. A depleted node ("Not enough stock") does not.
- **Stay beside work (S4).** With no affordable role verb, idle_skip WAITs in place when the role verb is advertised here but unaffordable. m03 used to walk away from relay-quarter REPAIR at energy 3. When an affordable role verb (other than CONSTRUCT/BUILD) is in the menu, MOVE is removed from the model's options. m04 used to walk off beside RECONSTRUCT_PUBLISH.
- **Explorer floor (S6).** The surveyor moves only at energy >= 2. It spent 38/60 turns at energy <= 1.

## D-054 The quartermaster goes to the custodian (S7)

SUPPLY only works in the same room. m02 harvested into the treasury wherever it stood while m03 sat short of cargo two rooms away. When the vault holds at least one supply's worth (3) and the custodian's own recorded position shows fewer than 6 aboard in another room, the quartermaster takes one step toward it before harvesting more.

## D-055 One public record per subject (S12)

m04 made 78 RECONSTRUCT_PUBLISH out of 300 turns and no new reconstructions. The engine offered 50 PUBLISH affordances, all for private drafts of one subject (`entity.salvage-cache`), so each publish only made one more draft of the same story public. The menu now offers one PUBLISH per subject, none for a subject the archivist already published (memory kind `published`), and no new RECONSTRUCT of a published subject. That frees attention for INSPECT and reconstructing other subjects.

## D-056 The founder welcomes newcomers (S11)

m01 has had nothing to do since the Compact was seated (0 role actions per 60 turns at energy 45+). MESSAGE is now a founder verb. The planner sends one welcome naming the Compact to each non-cohort, non-operator Player it meets, recorded as memory kind `welcomed`. The model never sees the founder's MESSAGE options. No engine change.

## D-057 A shared work queue drives custodian routing and supply (S8, S10)

Each agent writes the role work it sees in its own room to a map.db `work` table as (action, target, need). need is `''` when affordable, else materials, energy, attention or other. CONSTRUCT/BUILD and depleted nodes are left out, and each new look replaces that agent's rows for the room. Two consumers:
- **Routing (S10).** `route(me=...)` goes first to the nearest room where the agent itself saw role work, then falls back to `where_offered`. The custodian now heads for its own REPAIR/RESTORE targets rather than any room that once listed a matching verb.
- **Need (S8).** The custodian counts as needing cargo whenever its own work is blocked on materials, not only when it has fewer than 6 aboard. Live example: RESTORE of the archive annex needs 4 storage and was "no materials in hold" while it carried 2. The quartermaster's station step (D-054) uses the same signal.
All rows come from each agent's own observations. Nothing is inferred about other Players.
