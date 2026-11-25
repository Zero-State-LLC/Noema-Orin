
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
